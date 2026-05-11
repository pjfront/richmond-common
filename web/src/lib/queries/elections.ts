import {
  supabase,
  RICHMOND_FIPS,
  warnIfEmpty,
  nameToSlug,
  isGovernmentEntity,
  filterGovernmentEntityFlags,
  COLS_MEETING_LIST,
  COLS_MEETING_BANNER,
  COLS_FLAG_SUMMARY,
  COLS_PUBLIC_RECORD_LIST,
} from './_shared'
import RICHMOND_FILERS_DATA from '@/data/netfile-richmond-filers.json'
import type {
  Meeting,
  Official,
  AgendaItem,
  Motion,
  Vote,
  MeetingAttendance,
  ConflictFlag,
  ClosedSessionItem,
  NotableSpeaker,
  AgendaItemWithMotions,
  MotionWithVotes,
  MeetingDetail,
  DonorAggregate,
  DonorContribution,
  EconomicInterest,
  NextRequestRequest,
  PublicRecordsStats,
  DepartmentCompliance,
  Commission,
  CommissionMember,
  CommissionWithStats,
  CommissionStaleness,
  CategoryStats,
  ControversyItem,
  PairwiseAlignment,
  CategoryDivergence,
  DivergentMotionRow,
  DivergentMotion,
  DonorCategoryPattern,
  DonorOverlap,
  CategoryCount,
  TopicLabelCount,
  MeetingWithCounts,
  FinancialConnectionFlag,
  OfficialConnectionSummary,
  SearchResult,
  SearchResultType,
  SimilarItem,
  ContributionNarrativeData,
  ContributionRecord,
  BehstedPaymentNarrativeData,
  ItemVoteContext,
  RelatedAgendaItem,
  ItemInfluenceMapData,
  Election,
  ElectionCandidate,
  ElectionWithCandidates,
  CandidateFundraising,
  CandidateFundraisingDetail,
  CandidateTopDonor,
  CandidateDonorsByCycle,
  ContributionBreakdown,
  PublicCommentDetail,
  CommentTheme,
  ThemeNarrative,
  AgendaItemDetail,
  AgendaItemRef,
  AgendaItemSibling,
  RelatedTopicItem,
  CommunityComment,
  NeighborhoodCouncil,
  Provenance,
  FilingPeriodBriefing,
  PACAggregate,
  PACContributionRow,
  PACOutgoingRow,
  PACIndependentExpenditureRow,
} from '../types'
import { CONFIDENCE_PUBLISHED } from '../thresholds'
import { commentSourceToProvenance } from '../provenance'

// ── Election Cycle Tracking (B.24) ────────────────────────

export async function getElections(
  cityFips = RICHMOND_FIPS,
): Promise<Election[]> {
  const { data, error } = await supabase
    .from('elections')
    .select('*')
    .eq('city_fips', cityFips)
    .order('election_date', { ascending: false })

  if (error) {
    console.error('getElections query failed:', error)
    return [] as Election[]
  }
  return data as Election[]
}


/** Get the next upcoming election (for banners, CTAs). */
export async function getUpcomingElection(
  cityFips = RICHMOND_FIPS,
): Promise<Election | null> {
  const today = new Date().toISOString().split('T')[0]
  const { data, error } = await supabase
    .from('elections')
    .select('*')
    .eq('city_fips', cityFips)
    .gte('election_date', today)
    .order('election_date', { ascending: true })
    .limit(1)
    .single()

  if (error || !data) return null
  return data as Election
}


/**
 * URL slug for an election: "2026-primary", "2026-general", etc.
 * Inverse of getElectionBySlug. Lifted from /elections/page.tsx so the
 * layout (server) and Nav (client via prop) can construct the same link.
 */
export function electionToSlug(election: Pick<Election, 'election_date' | 'election_type'>): string {
  const year = election.election_date.split('-')[0]
  return `${year}-${election.election_type}`
}


/**
 * Find an election by slug (e.g. "2026-primary" → election_date 2026 + type primary).
 * Returns the election ID for use with getElectionWithCandidates/getElectionFundraisingSummary.
 */
/**
 * Latest current filing-period briefing for an election.
 *
 * One briefing row per (city, election, period_label) WHERE is_current.
 * Returns the most recent by period_end. Used by candidate-page sections
 * (F1–F4) and the future cross-candidate dashboard.
 *
 * Note: the candidate page is currently OperatorGate'd, so this is fetched
 * from a server component running with the SSR client. When the page
 * graduates to public, the RLS policy on filing_period_briefings will
 * gate visibility by publication_tier='public'.
 */
export async function getFilingPeriodBriefing(
  electionId: string,
  cityFips = RICHMOND_FIPS,
): Promise<FilingPeriodBriefing | null> {
  const { data, error } = await supabase
    .from('filing_period_briefings')
    .select(
      'id, city_fips, election_id, period_label, period_kind, ' +
        'period_start, period_end, filed_through, sections, section_tiers, ' +
        'provenance, contributions_considered, paper_filings_considered, ' +
        'publication_tier, is_current, generated_at',
    )
    .eq('city_fips', cityFips)
    .eq('election_id', electionId)
    .eq('is_current', true)
    .order('period_end', { ascending: false })
    .limit(1)
    .maybeSingle()

  if (error || !data) return null
  // Cast via unknown — Supabase's generated types don't yet know about
  // filing_period_briefings (table added in migration 099 / 2026-04-28).
  // The shape is enforced at runtime by the SELECT column list above.
  return data as unknown as FilingPeriodBriefing
}


export async function getElectionBySlug(
  slug: string,
  cityFips = RICHMOND_FIPS,
): Promise<Election | null> {
  // Parse slug: "YYYY-type" e.g. "2026-primary", "2024-general"
  const match = slug.match(/^(\d{4})-(primary|general|special|runoff)$/)
  if (!match) return null

  const [, yearStr, electionType] = match
  const yearStart = `${yearStr}-01-01`
  const yearEnd = `${yearStr}-12-31`

  const { data, error } = await supabase
    .from('elections')
    .select('*')
    .eq('city_fips', cityFips)
    .eq('election_type', electionType)
    .gte('election_date', yearStart)
    .lte('election_date', yearEnd)
    .limit(1)
    .single()

  if (error || !data) return null
  return data as Election
}


export async function getElectionWithCandidates(
  electionId: string,
  cityFips = RICHMOND_FIPS,
): Promise<ElectionWithCandidates | null> {
  const [{ data: election, error: electionError }, { data: candidates, error: candidatesError }] =
    await Promise.all([
      supabase
        .from('elections')
        .select('*')
        .eq('id', electionId)
        .eq('city_fips', cityFips)
        .single(),
      supabase
        .from('election_candidates')
        .select('*')
        .eq('election_id', electionId)
        .eq('city_fips', cityFips)
        .order('office_sought')
        .order('candidate_name'),
    ])

  if (electionError || !election) {
    console.error('getElectionWithCandidates failed:', electionError)
    return null
  }
  if (candidatesError) {
    console.error('getElectionCandidates failed:', candidatesError)
  }

  return {
    ...(election as Election),
    candidates: (candidates ?? []) as ElectionCandidate[],
  }
}


export async function getElectionFundraisingSummary(
  electionId: string,
  cityFips = RICHMOND_FIPS,
): Promise<CandidateFundraising[]> {
  // Use election_candidates joined with contributions via committee_id
  const { data: candidates, error: candidatesError } = await supabase
    .from('election_candidates')
    .select('id, candidate_name, office_sought, is_incumbent, status, committee_id')
    .eq('election_id', electionId)
    .eq('city_fips', cityFips)

  if (candidatesError || !candidates) {
    console.error('getElectionFundraisingSummary failed:', candidatesError)
    return []
  }

  const results: CandidateFundraising[] = []

  for (const candidate of candidates) {
    if (!candidate.committee_id) {
      results.push({
        candidate_name: candidate.candidate_name,
        office_sought: candidate.office_sought,
        is_incumbent: candidate.is_incumbent,
        status: candidate.status,
        total_raised: 0,
        contribution_count: 0,
        donor_count: 0,
        avg_contribution: 0,
        largest_contribution: 0,
        smallest_contribution: 0,
      })
      continue
    }

    const { data: contribs } = await supabase
      .from('contributions')
      .select('amount, donor_id')
      .eq('committee_id', candidate.committee_id)
      .eq('city_fips', cityFips)

    if (!contribs || contribs.length === 0) {
      results.push({
        candidate_name: candidate.candidate_name,
        office_sought: candidate.office_sought,
        is_incumbent: candidate.is_incumbent,
        status: candidate.status,
        total_raised: 0,
        contribution_count: 0,
        donor_count: 0,
        avg_contribution: 0,
        largest_contribution: 0,
        smallest_contribution: 0,
      })
      continue
    }

    const amounts = contribs.map((c) => c.amount)
    const totalRaised = amounts.reduce((sum, a) => sum + a, 0)
    const uniqueDonors = new Set(contribs.map((c) => c.donor_id))

    results.push({
      candidate_name: candidate.candidate_name,
      office_sought: candidate.office_sought,
      is_incumbent: candidate.is_incumbent,
      status: candidate.status,
      total_raised: totalRaised,
      contribution_count: contribs.length,
      donor_count: uniqueDonors.size,
      avg_contribution: contribs.length > 0 ? totalRaised / contribs.length : 0,
      largest_contribution: Math.max(...amounts),
      smallest_contribution: Math.min(...amounts),
    })
  }

  // Sort by total raised descending
  results.sort((a, b) => b.total_raised - a.total_raised)
  return results
}


/** Get an official's election history (all candidacies with election dates) */
export async function getOfficialElectionHistory(
  officialId: string,
  cityFips = RICHMOND_FIPS,
): Promise<(ElectionCandidate & { election_date: string; election_type: string })[]> {
  const { data, error } = await supabase
    .from('election_candidates')
    .select('*, elections!inner(election_date, election_type)')
    .eq('official_id', officialId)
    .eq('city_fips', cityFips)

  if (error || !data) {
    console.error('getOfficialElectionHistory failed:', error)
    return []
  }

  return data.map((row: Record<string, unknown>) => {
    const elections = row.elections as { election_date: string; election_type: string }
    return {
      ...(row as unknown as ElectionCandidate),
      election_date: elections.election_date,
      election_type: elections.election_type,
    }
  })
}


/** Get upcoming candidacies for all current officials (for listing page badges) */
export async function getCurrentCandidacies(
  cityFips = RICHMOND_FIPS,
): Promise<(ElectionCandidate & { election_date: string })[]> {
  const today = new Date().toISOString().slice(0, 10)
  const { data, error } = await supabase
    .from('election_candidates')
    .select('*, elections!inner(election_date)')
    .eq('city_fips', cityFips)
    .not('official_id', 'is', null)
    .in('status', ['filed', 'qualified'])

  if (error || !data) {
    console.error('getCurrentCandidacies failed:', error)
    return []
  }

  // Filter to future elections client-side (Supabase join filter syntax is tricky)
  return data
    .map((row: Record<string, unknown>) => {
      const elections = row.elections as { election_date: string }
      return {
        ...(row as unknown as ElectionCandidate),
        election_date: elections.election_date,
      }
    })
    .filter(c => c.election_date >= today)
}


// ─── Candidate Discovery (S21.5.7) ────────────────────────


/** Get top donors for a candidate by their committee_id */
export async function getCandidateTopDonors(
  committeeId: string,
  limit = 10,
  cityFips = RICHMOND_FIPS,
): Promise<CandidateTopDonor[]> {
  const { data, error } = await supabase
    .from('contributions')
    .select('amount, donors!inner(name, employer)')
    .eq('committee_id', committeeId)
    .eq('city_fips', cityFips)

  if (error || !data) {
    console.error('getCandidateTopDonors failed:', error)
    return []
  }

  // Aggregate by donor name
  const donorMap = new Map<string, { employer: string | null; total: number; count: number }>()
  for (const row of data) {
    const donor = (row as Record<string, unknown>).donors as {
      name: string
      employer: string | null
    }
    const nameLower = donor.name.toLowerCase()
    // Skip government entities (public financing, refunds, inter-committee transfers)
    if (/^(the )?(city|county|state|town) of\b/.test(nameLower)) continue

    const existing = donorMap.get(donor.name)
    if (existing) {
      existing.total += row.amount as number
      existing.count += 1
    } else {
      donorMap.set(donor.name, {
        employer: donor.employer,
        total: row.amount as number,
        count: 1,
      })
    }
  }

  return Array.from(donorMap.entries())
    .map(([name, d]) => ({
      donor_name: name,
      employer: d.employer,
      total_contributed: d.total,
      contribution_count: d.count,
    }))
    .sort((a, b) => b.total_contributed - a.total_contributed)
    .slice(0, limit)
}


/** Get contribution size breakdown for a candidate's committee */
export async function getCandidateContributionBreakdown(
  committeeId: string,
  cityFips = RICHMOND_FIPS,
): Promise<ContributionBreakdown> {
  const { data, error } = await supabase
    .from('contributions')
    .select('amount')
    .eq('committee_id', committeeId)
    .eq('city_fips', cityFips)

  if (error || !data) {
    return { small: 0, medium: 0, large: 0, major: 0, total_count: 0 }
  }

  let small = 0, medium = 0, large = 0, major = 0
  for (const row of data) {
    const amt = row.amount as number
    if (amt < 100) small++
    else if (amt < 500) medium++
    else if (amt < 1000) large++
    else major++
  }

  return { small, medium, large, major, total_count: data.length }
}


/**
 * Enhanced fundraising summary with top donors and breakdown per candidate.
 * Used on the election detail page for candidate discovery.
 */
export async function getCandidateFundraisingDetails(
  electionId: string,
  cityFips = RICHMOND_FIPS,
  electionDate?: string,
): Promise<CandidateFundraisingDetail[]> {
  // Cycle boundary: Jan 1 of the year before the election
  const cycleStart = electionDate
    ? `${new Date(electionDate + 'T00:00:00').getFullYear() - 1}-01-01`
    : null

  // Get candidates with committee linkage
  const { data: candidates, error } = await supabase
    .from('election_candidates')
    .select('id, candidate_name, office_sought, is_incumbent, status, committee_id, official_id')
    .eq('election_id', electionId)
    .eq('city_fips', cityFips)

  if (error || !candidates) {
    console.error('getCandidateFundraisingDetails failed:', error)
    return []
  }

  const emptyResult = (c: typeof candidates[number]): CandidateFundraisingDetail => ({
    id: c.id,
    candidate_name: c.candidate_name,
    office_sought: c.office_sought,
    is_incumbent: c.is_incumbent,
    status: c.status,
    committee_id: c.committee_id,
    official_id: c.official_id,
    total_raised: 0,
    contribution_count: 0,
    donor_count: 0,
    avg_contribution: 0,
    largest_contribution: 0,
    smallest_contribution: 0,
    top_donors: [],
    contribution_breakdown: { small: 0, medium: 0, large: 0, major: 0, total_count: 0 },
    earliest_contribution: null,
    latest_contribution: null,
    lifetime_raised: 0,
  })

  const results: CandidateFundraisingDetail[] = []

  for (const candidate of candidates) {
    if (!candidate.committee_id) {
      results.push(emptyResult(candidate))
      continue
    }

    // Fetch all contributions + donors in one query
    const { data: contribs } = await supabase
      .from('contributions')
      .select('amount, contribution_date, donor_id, donors!inner(name, employer)')
      .eq('committee_id', candidate.committee_id)
      .eq('city_fips', cityFips)

    if (!contribs || contribs.length === 0) {
      results.push(emptyResult(candidate))
      continue
    }

    // Lifetime total from all contributions
    const lifetimeRaised = contribs.reduce((sum, c) => sum + (c.amount as number), 0)

    // Partition: cycle contributions only (or all if no cycle boundary)
    const cycleContribs = cycleStart
      ? contribs.filter((c) => (c.contribution_date as string | null) != null && (c.contribution_date as string) >= cycleStart)
      : contribs

    // Earliest contribution across ALL contributions (for lifetime context line)
    const allDates = contribs
      .map((c) => c.contribution_date as string | null)
      .filter((d): d is string => d != null)
      .sort()
    const earliestContribution = allDates[0] ?? null

    // Aggregate from cycle subset
    const amounts = cycleContribs.map((c) => c.amount as number)
    const totalRaised = amounts.reduce((sum, a) => sum + a, 0)
    const uniqueDonors = new Set(cycleContribs.map((c) => c.donor_id))

    // Cycle date range
    const cycleDates = cycleContribs
      .map((c) => c.contribution_date as string | null)
      .filter((d): d is string => d != null)
      .sort()
    // Use cycle dates if available, fall back to all dates for lifetime-only display
    const latestContribution = (cycleDates[cycleDates.length - 1] ?? allDates[allDates.length - 1]) ?? null

    // Contribution breakdown (cycle only)
    let small = 0, medium = 0, large = 0, major = 0
    for (const amt of amounts) {
      if (amt < 100) small++
      else if (amt < 500) medium++
      else if (amt < 1000) large++
      else major++
    }

    // Top donors (cycle only)
    const donorMap = new Map<string, { employer: string | null; total: number; count: number }>()
    for (const row of cycleContribs) {
      const donor = (row as Record<string, unknown>).donors as {
        name: string
        employer: string | null
      }
      const nameLower = donor.name.toLowerCase()
      if (/^(the )?(city|county|state|town) of\b/.test(nameLower)) continue

      const existing = donorMap.get(donor.name)
      if (existing) {
        existing.total += row.amount as number
        existing.count += 1
      } else {
        donorMap.set(donor.name, {
          employer: donor.employer,
          total: row.amount as number,
          count: 1,
        })
      }
    }

    const topDonors = Array.from(donorMap.entries())
      .map(([name, d]) => ({
        donor_name: name,
        employer: d.employer,
        total_contributed: d.total,
        contribution_count: d.count,
      }))
      .sort((a, b) => b.total_contributed - a.total_contributed)
      .slice(0, 5)

    results.push({
      id: candidate.id,
      candidate_name: candidate.candidate_name,
      office_sought: candidate.office_sought,
      is_incumbent: candidate.is_incumbent,
      status: candidate.status,
      committee_id: candidate.committee_id,
      official_id: candidate.official_id,
      total_raised: totalRaised,
      contribution_count: cycleContribs.length,
      donor_count: uniqueDonors.size,
      avg_contribution: cycleContribs.length > 0 ? totalRaised / cycleContribs.length : 0,
      largest_contribution: amounts.length > 0 ? Math.max(...amounts) : 0,
      smallest_contribution: amounts.length > 0 ? Math.min(...amounts) : 0,
      top_donors: topDonors,
      contribution_breakdown: { small, medium, large, major, total_count: cycleContribs.length },
      earliest_contribution: earliestContribution,
      latest_contribution: latestContribution,
      lifetime_raised: lifetimeRaised,
    })
  }

  results.sort((a, b) => b.total_raised - a.total_raised)
  return results
}


// ─── Most-Commented Votes for a Candidate ─────────────────────────────────

export interface CommentedVoteRollEntry {
  official_name: string
  vote_choice: string
}

export interface CommentedVoteTheme {
  label: string
  narrative: string
  comment_count: number
}

export interface CommentedVote {
  candidate_vote: string
  item_title: string
  summary_headline: string | null
  plain_language_summary: string | null
  item_id: string
  meeting_id: string
  topic_label: string | null
  public_comment_count: number
  meeting_date: string
  motion_result: string
  roll_call: CommentedVoteRollEntry[]
  themes: CommentedVoteTheme[]
  // Provenance of the comment_themes shown for this item, derived at
  // query time from public_comments.source. Null when no comments
  // exist or the source is unknown — VotedItemCard falls back to a
  // deliberately vague catch-all label.
  theme_provenance: Provenance | null
}

export async function getMostCommentedVotes(
  officialId: string,
  limit = 5,
): Promise<CommentedVote[]> {
  // Step 1: Get this official's votes on items with public comments
  const { data: voteData, error } = await supabase
    .from('votes')
    .select(`
      vote_choice,
      motions!inner (
        id,
        result,
        agenda_items!inner (
          id,
          title,
          summary_headline,
          plain_language_summary,
          topic_label,
          public_comment_count,
          meetings!inner (id, meeting_date)
        )
      )
    `)
    .eq('official_id', officialId)

  if (error || !voteData) {
    console.error('getMostCommentedVotes failed:', error)
    return []
  }

  // Flatten, filter, dedup, pick top N
  interface RawRow {
    candidateVote: string
    motionId: string
    motionResult: string
    itemId: string
    itemTitle: string
    summaryHeadline: string | null
    summary: string | null
    topicLabel: string | null
    commentCount: number
    meetingId: string
    meetingDate: string
  }

  const rows: RawRow[] = []
  const seenItems = new Set<string>()
  for (const vote of voteData) {
    const motion = (vote as Record<string, unknown>).motions as {
      id: string; result: string
      agenda_items: {
        id: string; title: string; summary_headline: string | null
        plain_language_summary: string | null; topic_label: string | null
        public_comment_count: number | null
        meetings: { id: string; meeting_date: string }
      }
    }
    const item = motion.agenda_items
    if (!item.public_comment_count || item.public_comment_count === 0) continue
    if (seenItems.has(item.id)) continue
    seenItems.add(item.id)
    rows.push({
      candidateVote: vote.vote_choice as string,
      motionId: motion.id,
      motionResult: motion.result,
      itemId: item.id,
      itemTitle: item.title,
      summaryHeadline: item.summary_headline,
      summary: item.plain_language_summary,
      topicLabel: item.topic_label,
      commentCount: item.public_comment_count,
      meetingId: item.meetings.id,
      meetingDate: item.meetings.meeting_date,
    })
  }

  const topRows = rows
    .sort((a, b) => b.commentCount - a.commentCount)
    .slice(0, limit)

  if (topRows.length === 0) return []

  // Step 2: Fetch full roll call for these motions
  const motionIds = topRows.map((r) => r.motionId)
  const { data: rollData } = await supabase
    .from('votes')
    .select('motion_id, official_name, vote_choice')
    .in('motion_id', motionIds)

  const rollByMotion = new Map<string, CommentedVoteRollEntry[]>()
  for (const v of rollData ?? []) {
    const mid = v.motion_id as string
    const list = rollByMotion.get(mid) ?? []
    list.push({ official_name: v.official_name as string, vote_choice: v.vote_choice as string })
    rollByMotion.set(mid, list)
  }

  // Step 3: Fetch themes for these items
  const itemIds = topRows.map((r) => r.itemId)
  const { data: themeData } = await supabase
    .from('item_theme_narratives')
    .select('agenda_item_id, narrative, comment_count, comment_themes(label)')
    .in('agenda_item_id', itemIds)
    .order('comment_count', { ascending: false })

  const themesByItem = new Map<string, CommentedVoteTheme[]>()
  for (const t of themeData ?? []) {
    const aid = t.agenda_item_id as string
    const list = themesByItem.get(aid) ?? []
    const theme = (t as Record<string, unknown>).comment_themes as { label: string } | null
    if (theme) {
      list.push({
        label: theme.label,
        narrative: t.narrative as string,
        comment_count: t.comment_count as number,
      })
    }
    themesByItem.set(aid, list)
  }

  // Step 4: Fetch comment source per item so the rendered theme
  // attribution can be specific (audit row #6 — was a vague "meeting
  // records" catch-all because this query didn't surface the source).
  const { data: sourceData } = await supabase
    .from('public_comments')
    .select('agenda_item_id, source')
    .in('agenda_item_id', itemIds)
    .limit(itemIds.length * 50)

  const sourceByItem = new Map<string, string | null>()
  for (const c of sourceData ?? []) {
    const aid = c.agenda_item_id as string
    if (!sourceByItem.has(aid)) {
      sourceByItem.set(aid, (c.source as string | null) ?? null)
    }
  }

  // Assemble results
  return topRows.map((r) => ({
    candidate_vote: r.candidateVote,
    item_title: r.itemTitle,
    summary_headline: r.summaryHeadline,
    plain_language_summary: r.summary,
    item_id: r.itemId,
    meeting_id: r.meetingId,
    topic_label: r.topicLabel,
    public_comment_count: r.commentCount,
    meeting_date: r.meetingDate,
    motion_result: r.motionResult,
    roll_call: rollByMotion.get(r.motionId) ?? [],
    themes: themesByItem.get(r.itemId) ?? [],
    theme_provenance: commentSourceToProvenance(sourceByItem.get(r.itemId) ?? null),
  }))
}

