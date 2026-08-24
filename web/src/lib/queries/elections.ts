import { cache } from 'react'
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
  COLS_CONTRIBUTION_PUBLIC,
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
  CandidateFundingBreakdown,
  CandidateFundingBucket,
  CandidateIESupporter,
  ContributorTypeBucket,
  ContributionMatrix,
  PublicCommentDetail,
  CommentTheme,
  ThemeNarrative,
  AgendaItemDetail,
  AgendaItemRef,
  AgendaItemSibling,
  RelatedTopicItem,
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
import { addToMatrix, emptyMatrix } from '../contributionBuckets'

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


export const getElectionBySlug = cache(async function getElectionBySlug(
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
})


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


/**
 * D56b Option 1: trust each candidate's own Form 460 cycle-to-date total.
 *
 * Looks up `form_summary_cache` rows for this committee, picks the latest
 * (by period_end DESC), and returns its `monetary_cycle_to_date` plus the
 * period_end for display as "raised $X through [date]".
 *
 * Returns null when no Form 460 has been filed yet (or extracted). Callers
 * fall back to summing DB rows in that case.
 *
 * Why "cycle_to_date" not "this_period": multi-period campaigns (Zepeda,
 * Wilson) have multiple Form 460s per cycle. Cycle-to-date on the latest
 * filing is the candidate's own certified rollup across periods and
 * handles cycle resets correctly (Zepeda's 2024-cycle money doesn't
 * leak into his 2026-cycle display).
 *
 * Why use form cover total not "Form 460 + supplemental Form 497s":
 * publishing-policy decision in D56b, 2026-05-17. We defer to each
 * candidate's own legal filing for the headline number. Form 497 late-
 * contribution disclosures remain visible in the donor list but don't
 * bump the headline; if a candidate omits a Form 497 contribution from
 * their next Form 460, that's a compliance question for FPPC, not ours
 * to surface via a custom calculation.
 */
async function getLatestForm460Total(
  committeeId: string,
): Promise<{ total: number; throughDate: string; filingId: string } | null> {
  const { data: committee, error: cErr } = await supabase
    .from('committees')
    .select('name')
    .eq('id', committeeId)
    .maybeSingle()
  if (cErr || !committee) return null

  const { data: summaries, error: sErr } = await supabase
    .from('form_summary_cache')
    .select('filing_id, summary')
    .eq('committee', committee.name)
  if (sErr || !summaries || summaries.length === 0) return null

  // Pick latest by period_end DESC. Migration 115's unique index on
  // (committee, period_start, period_end) guarantees no two rows share a
  // period, so this resolves to a single canonical row per period and the
  // sort picks the most recent period.
  const ranked = summaries
    .map((s) => {
      const summaryObj = s.summary as Record<string, unknown> | null
      const periodEnd =
        summaryObj && typeof summaryObj.period_end === 'string'
          ? summaryObj.period_end
          : null
      const cycleTotalRaw =
        summaryObj && (typeof summaryObj.monetary_cycle_to_date === 'string' ||
                       typeof summaryObj.monetary_cycle_to_date === 'number')
          ? Number(summaryObj.monetary_cycle_to_date)
          : NaN
      return {
        filingId: s.filing_id as string,
        periodEnd,
        cycleTotal: cycleTotalRaw,
      }
    })
    .filter((r): r is { filingId: string; periodEnd: string; cycleTotal: number } =>
      r.periodEnd !== null && Number.isFinite(r.cycleTotal),
    )
    .sort((a, b) => b.periodEnd.localeCompare(a.periodEnd))

  if (ranked.length === 0) return null
  const latest = ranked[0]
  return {
    total: latest.cycleTotal,
    throughDate: latest.periodEnd,
    filingId: latest.filingId,
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
    const dbSum = amounts.reduce((sum, a) => sum + a, 0)
    const uniqueDonors = new Set(contribs.map((c) => c.donor_id))

    // D56b Option 1: prefer the candidate's own Form 460 cycle-to-date
    // total over the sum of DB rows. See getLatestForm460Total() above
    // for rationale.
    const form460 = await getLatestForm460Total(candidate.committee_id)
    const totalRaised = form460 ? form460.total : dbSum

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
    contribution_matrix: emptyMatrix(),
    bucket_grid_consistent: true,  // no data → nothing to disagree
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

    // Fetch all contributions + donors in one query. `contributor_type`
    // drives the source-type axis of the bucket matrix below (migration
    // 048 + src/contributor_classifier.py; lib/contributionBuckets.ts
    // maps the raw enum to the public display key).
    const { data: contribs } = await supabase
      .from('contributions')
      .select('amount, contribution_date, donor_id, contributor_type, donors!inner(name, employer)')
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
    const dbSum = amounts.reduce((sum, a) => sum + a, 0)
    const uniqueDonors = new Set(cycleContribs.map((c) => c.donor_id))

    // D56b Option 1: prefer the candidate's own Form 460 cycle-to-date
    // total over the sum of DB rows. See getLatestForm460Total() above
    // for rationale (it's defined earlier in this file). The donor list,
    // counts, and breakdowns below all still come from DB rows — only
    // the headline total defers to the form. Form 497 contributions
    // remain visible in the donor list.
    const form460 = await getLatestForm460Total(candidate.committee_id)
    const totalRaised = form460 ? form460.total : dbSum

    // D56b verification (2026-05-22): when the candidate has a Form 460,
    // the headline shows the form total. But the bucket grid below sums
    // DB rows directly — so if Form 497 late-filings inflate DB beyond
    // the form (Jimenez, Brandon Evans cases) or DB undercounts the form
    // (Anderson paper-filing case), headline and grid disagree by a
    // material amount. The flag below tells the consuming component to
    // hide the grid for those candidates. $1 tolerance handles penny
    // rounding — there's no ambiguous middle ground in practice (clean
    // candidates show 0.00 drift; mismatched candidates show 30%+).
    const bucketGridConsistent = form460
      ? Math.abs(form460.total - dbSum) <= 1
      : true

    // Cycle date range
    const cycleDates = cycleContribs
      .map((c) => c.contribution_date as string | null)
      .filter((d): d is string => d != null)
      .sort()
    // Use cycle dates if available, fall back to all dates for lifetime-only display
    const latestContribution = (cycleDates[cycleDates.length - 1] ?? allDates[allDates.length - 1]) ?? null

    // Contribution bucket matrix (cycle only). 5 amount buckets keyed
    // on California campaign-finance regulatory thresholds × 4 source
    // types from contributor_type. See lib/contributionBuckets.ts for
    // the boundary rationale and primary-source citations.
    const matrix: ContributionMatrix = emptyMatrix()
    for (const row of cycleContribs) {
      addToMatrix(matrix, {
        amount: row.amount as number,
        contributor_type: (row as { contributor_type: string | null }).contributor_type,
      })
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
      contribution_matrix: matrix,
      bucket_grid_consistent: bucketGridConsistent,
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


// ── Candidate funding artifact (operator-only, S24) ───────────────────
//
// Powers /elections/[slug]/mayor/funding. Two queries: the candidate's
// own controlled-committee breakdown by contributor_type, and the IE
// supporters operating outside their committee. Both narrate where the
// money actually comes from — answering the "no corporate donations" /
// "special interests" claims that dominate election framing.

/** Aggregate a candidate's controlled-committee contributions by
 *  contributor_type (individual, union, corporate, pac_ie, other). Each
 *  bucket includes top entities so the funding panel can name names
 *  (e.g., which union PACs, which corporations). Returns null when the
 *  committee has no contributions yet. */
export async function getCandidateFundingBreakdown(
  committeeId: string,
  cityFips = RICHMOND_FIPS,
): Promise<CandidateFundingBreakdown | null> {
  if (!committeeId) return null

  const { data, error } = await supabase
    .from('contributions')
    .select(`${COLS_CONTRIBUTION_PUBLIC}, donors!inner(name, employer)`)
    .eq('committee_id', committeeId)
    .eq('city_fips', cityFips)
    .order('contribution_date', { ascending: false })
    .range(0, 9999)

  if (error) {
    console.error('getCandidateFundingBreakdown query failed:', error)
    return null
  }
  if (!data || data.length === 0) return null

  type BucketAcc = {
    count: number
    total: number
    donors: Map<string, { total: number; count: number }>
  }
  const buckets = new Map<ContributorTypeBucket, BucketAcc>()
  const donorIds = new Set<string>()
  let totalRaised = 0
  let lastContribDate: string | null = null
  let lastUpdatedAt: string | null = null

  for (const row of data) {
    const rawType = (row.contributor_type as string | null) ?? 'other'
    const type: ContributorTypeBucket = (
      ['individual', 'union', 'corporate', 'pac_ie', 'other'].includes(rawType)
        ? rawType
        : 'other'
    ) as ContributorTypeBucket
    const amount = Number(row.amount ?? 0)
    const donor = (row as Record<string, unknown>).donors as { name: string }
    const donorId = row.donor_id as string

    totalRaised += amount
    donorIds.add(donorId)

    const contribDate = row.contribution_date as string | null
    if (contribDate && (!lastContribDate || contribDate > lastContribDate)) {
      lastContribDate = contribDate
    }
    const createdAt = row.created_at as string | null
    if (createdAt && (!lastUpdatedAt || createdAt > lastUpdatedAt)) {
      lastUpdatedAt = createdAt
    }

    let bucket = buckets.get(type)
    if (!bucket) {
      bucket = { count: 0, total: 0, donors: new Map() }
      buckets.set(type, bucket)
    }
    bucket.count += 1
    bucket.total += amount

    const existing = bucket.donors.get(donor.name)
    if (existing) {
      existing.total += amount
      existing.count += 1
    } else {
      bucket.donors.set(donor.name, { total: amount, count: 1 })
    }
  }

  const bucketArr: CandidateFundingBucket[] = Array.from(buckets.entries())
    .map(([type, b]) => ({
      contributor_type: type,
      contribution_count: b.count,
      total_amount: b.total,
      top_donors: Array.from(b.donors.entries())
        .map(([name, d]) => ({ name, total: d.total, count: d.count }))
        .sort((a, b) => b.total - a.total)
        .slice(0, 5),
    }))
    .sort((a, b) => b.total_amount - a.total_amount)

  return {
    committee_id: committeeId,
    total_raised: totalRaised,
    contribution_count: data.length,
    donor_count: donorIds.size,
    last_contribution_date: lastContribDate,
    last_updated_at: lastUpdatedAt,
    buckets: bucketArr,
  }
}


/** Find independent expenditure committees supporting (or opposing) a
 *  candidate, with funding-in and spending-out aggregated per supporter.
 *
 *  Two source streams reconciled by committee name:
 *  1. committees rows whose name matches "supporting [lastName]" — these
 *     are IE committees we can identify before they've filed any
 *     expenditures. Catches Anderson's Safe Richmond Neighborhoods
 *     ($30K POA seed, $0 spent yet).
 *  2. independent_expenditures rows where candidate_name matches —
 *     catches IEs that have already spent but whose committee row may
 *     not match a naming pattern (e.g., EBWF's generic name doesn't
 *     contain "Jimenez", but their expenditures do).
 *
 *  Pass the candidate's last name (or distinctive name fragment); we
 *  use ILIKE so partial matches work. Filter is intentionally permissive
 *  — operator review before public graduation is the safeguard against
 *  name-collision false positives. */
export async function getCandidateIESupport(
  candidateLastName: string,
  cityFips = RICHMOND_FIPS,
): Promise<CandidateIESupporter[]> {
  if (!candidateLastName) return []

  // Stream 1: IE-style committees identified by name
  const { data: ieCommittees } = await supabase
    .from('committees')
    .select('id, name')
    .eq('city_fips', cityFips)
    .ilike('name', `%supporting%${candidateLastName}%`)

  // Stream 2: IEs already spent on behalf of candidate
  const { data: ieExpenditures } = await supabase
    .from('independent_expenditures')
    .select('committee_name, support_or_oppose, amount, expenditure_date')
    .eq('city_fips', cityFips)
    .ilike('candidate_name', `%${candidateLastName}%`)
    .order('expenditure_date', { ascending: false })
    .range(0, 9999)

  // Key supporters by lowercased committee name so the two streams merge
  // when they share an IE.
  const supporterMap = new Map<string, CandidateIESupporter>()
  const keyOf = (name: string) => name.trim().toLowerCase()

  // Seed from name-matched committees
  for (const c of ieCommittees ?? []) {
    const name = c.name as string
    supporterMap.set(keyOf(name), {
      ie_committee_id: c.id as string,
      ie_committee_name: name,
      support_or_oppose: 'S', // "supporting [name]" implies support
      ie_funds_raised: 0,
      ie_funds_raised_count: 0,
      ie_top_funders: [],
      ie_funds_spent: 0,
      ie_funds_spent_count: 0,
      latest_activity_date: null,
    })
  }

  // Fetch contributions INTO the name-matched IE committees (this is
  // how the $30K POA seed shows up before any expenditures are filed)
  const ieCommitteeIds = (ieCommittees ?? []).map((c) => c.id as string)
  if (ieCommitteeIds.length > 0) {
    const { data: ieFunders } = await supabase
      .from('contributions')
      .select('amount, contribution_date, committee_id, donors!inner(name)')
      .in('committee_id', ieCommitteeIds)
      .eq('city_fips', cityFips)
      .range(0, 9999)

    // Build per-supporter funder maps for top_funders aggregation
    const fundersByKey = new Map<string, Map<string, { total: number; count: number }>>()
    const committeeIdToKey = new Map<string, string>(
      (ieCommittees ?? []).map((c) => [c.id as string, keyOf(c.name as string)]),
    )

    for (const f of ieFunders ?? []) {
      const key = committeeIdToKey.get(f.committee_id as string)
      if (!key) continue
      const supporter = supporterMap.get(key)
      if (!supporter) continue
      const amount = Number(f.amount ?? 0)
      supporter.ie_funds_raised += amount
      supporter.ie_funds_raised_count += 1
      const contribDate = f.contribution_date as string | null
      if (
        contribDate &&
        (!supporter.latest_activity_date || contribDate > supporter.latest_activity_date)
      ) {
        supporter.latest_activity_date = contribDate
      }

      const donor = (f as Record<string, unknown>).donors as { name: string }
      let donorMap = fundersByKey.get(key)
      if (!donorMap) {
        donorMap = new Map()
        fundersByKey.set(key, donorMap)
      }
      const existing = donorMap.get(donor.name)
      if (existing) {
        existing.total += amount
        existing.count += 1
      } else {
        donorMap.set(donor.name, { total: amount, count: 1 })
      }
    }

    for (const [key, donorMap] of fundersByKey) {
      const supporter = supporterMap.get(key)
      if (!supporter) continue
      supporter.ie_top_funders = Array.from(donorMap.entries())
        .map(([name, d]) => ({ name, total: d.total }))
        .sort((a, b) => b.total - a.total)
        .slice(0, 5)
    }
  }

  // Merge expenditure-stream rows by committee_name
  for (const e of ieExpenditures ?? []) {
    const name = (e.committee_name as string | null) ?? ''
    if (!name) continue
    const key = keyOf(name)
    let supporter = supporterMap.get(key)
    if (!supporter) {
      supporter = {
        ie_committee_id: null,
        ie_committee_name: name,
        support_or_oppose: (e.support_or_oppose as 'S' | 'O' | null) ?? null,
        ie_funds_raised: 0,
        ie_funds_raised_count: 0,
        ie_top_funders: [],
        ie_funds_spent: 0,
        ie_funds_spent_count: 0,
        latest_activity_date: null,
      }
      supporterMap.set(key, supporter)
    } else if (supporter.support_or_oppose === null) {
      supporter.support_or_oppose = (e.support_or_oppose as 'S' | 'O' | null) ?? null
    }
    supporter.ie_funds_spent += Number(e.amount ?? 0)
    supporter.ie_funds_spent_count += 1
    const expDate = e.expenditure_date as string | null
    if (
      expDate &&
      (!supporter.latest_activity_date || expDate > supporter.latest_activity_date)
    ) {
      supporter.latest_activity_date = expDate
    }
  }

  return Array.from(supporterMap.values()).sort(
    (a, b) => b.ie_funds_spent + b.ie_funds_raised - (a.ie_funds_spent + a.ie_funds_raised),
  )
}

