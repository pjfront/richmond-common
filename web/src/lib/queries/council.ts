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
  COLS_FORM700_FILING,
  COLS_OFFICIAL_FULL,
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
  Form700Filing,
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
  PublicCommentDetail,
  CommentTheme,
  ThemeNarrative,
  AgendaItemDetail,
  AgendaItemRef,
  AgendaItemSibling,
  NeighborhoodCouncil,
  Provenance,
  FilingPeriodBriefing,
  PACAggregate,
  PACContributionRow,
  PACOutgoingRow,
  PACIndependentExpenditureRow,
  OfficialVotingRecordRow,
} from '../types'
import { CONFIDENCE_PUBLISHED } from '../thresholds'
import { commentSourceToProvenance } from '../provenance'
import { cache } from 'react'
import { unstable_cache } from 'next/cache'
import { OFFICIALS_CACHE_SECONDS } from '../read-path-cache'
import { failReadPath, ReadPathUnavailableError } from '../read-path-unavailable'

// ─── Officials ───────────────────────────────────────────────

/** Council-level roles used to filter the /council listing page. */
const COUNCIL_ROLES = [
  'mayor', 'vice_mayor', 'councilmember', 'council_member', 'City/Town Council Member',
]

/** Role priority for deduplication: lower = higher priority. */
const ROLE_PRIORITY: Record<string, number> = {
  mayor: 1,
  vice_mayor: 2,
  councilmember: 3,
  council_member: 4,
  'City/Town Council Member': 5,
}

/** Common title prefixes to strip before deduplication. */
const TITLE_PREFIXES = [
  'mayor', 'vice mayor', 'councilmember', 'council member',
  'president', 'vice president',
]

/**
 * Build a dedup key that normalizes name order so "Last, First" and
 * "First Last" resolve to the same key. Strips title prefixes (e.g.,
 * "Mayor Tom Butt" -> same key as "Tom Butt"), punctuation, lowercases,
 * and sorts name parts alphabetically.
 */
function nameDeduplicationKey(name: string): string {
  let normalized = name.toLowerCase().replace(/[,.'"-]/g, '')
  // Strip title prefixes so "Mayor Butt" matches "Tom Butt" etc.
  for (const prefix of TITLE_PREFIXES) {
    if (normalized.startsWith(prefix + ' ')) {
      normalized = normalized.slice(prefix.length + 1)
      break
    }
  }
  return normalized
    .split(/\s+/)
    .filter(Boolean)
    .sort()
    .join(' ')
}

/**
 * Deduplicate officials that share the same name in different formats
 * (e.g., "Eduardo Martinez" vs "Martinez, Eduardo" from different scrapers).
 * Keeps the record with the highest-priority council role.
 */
function deduplicateOfficials(officials: Official[]): Official[] {
  const byKey = new Map<string, Official>()
  for (const o of officials) {
    const key = nameDeduplicationKey(o.name)
    const existing = byKey.get(key)
    if (!existing) {
      byKey.set(key, o)
    } else {
      const existingPri = ROLE_PRIORITY[existing.role] ?? 99
      const newPri = ROLE_PRIORITY[o.role] ?? 99
      if (newPri < existingPri) {
        byKey.set(key, o)
      }
    }
  }
  return Array.from(byKey.values())
}

const getAllOfficialsCached = unstable_cache(
  async (cityFips: string): Promise<Official[]> => {
    const { data, error } = await supabase
      .from('officials')
      .select(COLS_OFFICIAL_FULL)
      .eq('city_fips', cityFips)
      .order('name')

    if (error) failReadPath('Officials', error)

    warnIfEmpty('getOfficials', data)
    return (data ?? []) as unknown as Official[]
  },
  ['full-officials-read-v1'],
  { revalidate: OFFICIALS_CACHE_SECONDS },
)

export async function getOfficials(
  cityFips = RICHMOND_FIPS,
  opts: { currentOnly?: boolean; councilOnly?: boolean } = {},
) {
  let officials: Official[]
  try {
    officials = await getAllOfficialsCached(cityFips)
  } catch (error) {
    // Pull-request CI explicitly uses an unreachable Supabase URL so builds
    // cannot read production data. Keep that one build boundary deterministic
    // without caching the empty fallback: the cached read still throws above.
    // Every real build/runtime context remains fail-closed.
    if (
      process.env.RICHMOND_BUILD_USES_PRODUCTION_DATA !== 'false'
      || !(error instanceof ReadPathUnavailableError)
    ) {
      throw error
    }

    console.warn(
      '[Richmond Commons] Officials unavailable during explicitly inert CI build; using an empty build-only fallback.',
    )
    officials = []
  }

  const filtered = officials.filter((official) => (
    (!opts.currentOnly || official.is_current)
    && (!opts.councilOnly || COUNCIL_ROLES.includes(official.role))
  ))

  return deduplicateOfficials(filtered)
}

export const getOfficialBySlug = cache(async function getOfficialBySlug(
  slug: string,
  cityFips = RICHMOND_FIPS,
) {
  const officials = await getOfficials(cityFips)

  // Primary: exact slug match
  const match = officials.find(
    (o) => o.name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '') === slug
  )
  if (match) return match

  // Fallback: match by sorted name parts (handles "martinez-eduardo" → "Eduardo Martinez")
  const slugKey = slug.replace(/-/g, ' ').split(/\s+/).filter(Boolean).sort().join(' ')
  return officials.find(
    (o) => nameDeduplicationKey(o.name) === slugKey
  ) ?? null
})

export async function getOfficialVotingRecord(
  officialId: string,
): Promise<OfficialVotingRecordRow[]> {
  // Migration 144 is intentionally preview-gated. Keep the pending RPC local
  // until authoritative preview typegen adds it to database.types.ts; do not
  // hand-edit the generated file ahead of the schema.
  const pendingRpcClient = supabase as unknown as {
    rpc: (
      name: 'get_official_voting_record',
      args: { p_official_id: string },
    ) => Promise<{
      data: unknown[] | null
      error: unknown
    }>
  }
  const { data, error } = await pendingRpcClient.rpc('get_official_voting_record', {
    p_official_id: officialId,
  })

  if (error) failReadPath('Official voting record', error)

  return (data ?? []) as unknown as OfficialVotingRecordRow[]
}

const COLS_OFFICIAL_CONTRIBUTION_COMMITTEES = 'id, name, filer_id'
const COLS_OFFICIAL_CONTRIBUTIONS = 'id, committee_id, amount, contribution_date, contribution_type, filing_id, source, donors!inner(name, employer, donor_pattern)'
const HISTORICAL_CONTRIBUTION_PAGE_SIZE = 1000
const MAX_HISTORICAL_CONTRIBUTIONS = 10000
const MAX_HISTORICAL_CONTRIBUTION_PAGES = 20

export async function getOfficialContributions(
  officialId: string,
  cityFips = RICHMOND_FIPS
): Promise<DonorContribution[]> {
  // Keep the directly linked historical committees. Current candidate finance
  // uses its separate reviewed projection; do not union its legacy rows here.
  const { data: committees, count: committeeCount, error: committeeError } = await supabase
    .from('committees')
    .select(COLS_OFFICIAL_CONTRIBUTION_COMMITTEES, { count: 'exact' })
    .eq('official_id', officialId)
    .eq('city_fips', cityFips)
    .order('id')
    .limit(100)

  if (committeeError) failReadPath('Historical contribution committees', committeeError)
  if (committeeCount == null || !Number.isSafeInteger(committeeCount) || committeeCount < 0 || committeeCount > 100 || (committees?.length ?? 0) !== committeeCount) {
    failReadPath('Historical contribution committees', new Error('Committee lookup was incomplete'))
  }

  const committeeIds = (committees ?? []).map((c) => c.id)
  if (committeeIds.length === 0) return []
  const committeeById = new Map((committees ?? []).map((committee) => [committee.id, committee]))

  // Exact counts prevent a server row cap or an unexpectedly short page from
  // masquerading as the complete historical subtotal. A changing count or
  // duplicate page fails revalidation, preserving the previous successful ISR.
  const results: DonorContribution[] = []
  const seenIds = new Set<string>()
  let offset = 0
  let pages = 0
  let expectedCount: number | null = null
  do {
    if (++pages > MAX_HISTORICAL_CONTRIBUTION_PAGES) {
      failReadPath('Historical contributions', new Error('Historical contribution page budget was exhausted'))
    }
    const { data, error, count } = await supabase
      .from('contributions')
      .select(COLS_OFFICIAL_CONTRIBUTIONS, { count: 'exact' })
      .in('committee_id', committeeIds)
      .eq('city_fips', cityFips)
      .order('contribution_date', { ascending: true })
      .order('id', { ascending: true })
      .range(offset, offset + HISTORICAL_CONTRIBUTION_PAGE_SIZE - 1)

    if (error) failReadPath('Historical contributions', error)
    if (count == null || !Number.isSafeInteger(count) || count < 0 || count > MAX_HISTORICAL_CONTRIBUTIONS || (expectedCount != null && count !== expectedCount)) {
      failReadPath('Historical contributions', new Error('Historical contribution coverage changed or exceeded its bound'))
    }
    expectedCount = count
    const rows = data ?? []
    if (rows.length > HISTORICAL_CONTRIBUTION_PAGE_SIZE || offset + rows.length > count || (!rows.length && offset < count)) {
      failReadPath('Historical contributions', new Error('Historical contribution page was incomplete'))
    }
    for (const row of rows) {
      const committee = committeeById.get(row.committee_id)
      const donor = (row as Record<string, unknown>).donors as {
        name: string
        employer: string | null
        donor_pattern: string | null
      }
      const amount = Number(row.amount)
      if (!committee || typeof row.id !== 'string' || seenIds.has(row.id) || row.amount == null || !Number.isFinite(amount)
          || typeof row.contribution_date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(row.contribution_date)
          || typeof donor?.name !== 'string' || !donor.name.trim()) {
        failReadPath('Historical contributions', new Error('Historical contribution identity or amount was invalid'))
      }
      seenIds.add(row.id)

      // Preserve the existing government-entity exclusion for this historical
      // donor list. The separate finance projection retains event-kind context.
      const nameLower = donor.name.toLowerCase()
      if (/^(the )?(city|county|state|town) of\b/.test(nameLower)) continue

      const filingId = typeof row.filing_id === 'string' && /^[0-9]{6,12}$/.test(row.filing_id) ? row.filing_id : null
      results.push({
        donor_name: donor.name,
        donor_employer: donor.employer,
        donor_pattern: donor.donor_pattern,
        amount,
        contribution_date: row.contribution_date as string,
        contribution_type: row.contribution_type as string,
        source: row.source as string,
        committee_name: committee.name,
        committee_fppc_id: committee.filer_id,
        filing_id: filingId,
        source_url: filingId && ['city_clerk', 'netfile', 'netfile_paper'].includes(row.source)
          ? `https://netfile.com/Connect2/api/public/image/${filingId}` : null,
      })
    }
    offset += rows.length
  } while (offset < expectedCount)

  return results
}

/** All past general election dates for cycle-based contribution filtering */
export async function getPastElectionDates(
  cityFips = RICHMOND_FIPS,
): Promise<string[]> {
  const today = new Date().toISOString().split('T')[0]
  const { data } = await supabase
    .from('elections')
    .select('election_date')
    .eq('city_fips', cityFips)
    .eq('election_type', 'general')
    .lte('election_date', today)
    .order('election_date', { ascending: true })

  return (data ?? []).map((d) => d.election_date as string)
}

export async function getEconomicInterests(
  officialId: string,
  cityFips = RICHMOND_FIPS
): Promise<EconomicInterest[]> {
  const { data, error } = await supabase
    .from('economic_interests')
    .select(`
      id, city_fips, official_id, filing_id, filing_year,
      schedule, interest_type, description, value_range,
      location, source_url, document_id, created_at,
      form700_filings (
        statement_type, period_start, period_end,
        filer_name, source, source_url
      )
    `)
    .eq('official_id', officialId)
    .eq('city_fips', cityFips)
    .order('filing_year', { ascending: false })

  if (error) {
    console.error('getEconomicInterests query failed:', error)
    return []
  }

  return (data ?? []).map((row) => {
    const filing = (row as Record<string, unknown>).form700_filings as {
      statement_type: string | null
      period_start: string | null
      period_end: string | null
      filer_name: string | null
      source: string | null
      source_url: string | null
    } | null
    return {
      id: row.id as string,
      city_fips: row.city_fips as string,
      official_id: row.official_id as string | null,
      filing_id: row.filing_id as string | null,
      filing_year: row.filing_year as number,
      schedule: row.schedule as EconomicInterest['schedule'],
      interest_type: row.interest_type as EconomicInterest['interest_type'],
      description: row.description as string,
      value_range: row.value_range as string | null,
      location: row.location as string | null,
      source_url: row.source_url as string | null,
      document_id: row.document_id as string | null,
      created_at: row.created_at as string,
      statement_type: filing?.statement_type ?? null,
      period_start: filing?.period_start ?? null,
      period_end: filing?.period_end ?? null,
      filer_name: filing?.filer_name ?? null,
      filing_source: filing?.source ?? null,
      filing_source_url: filing?.source_url ?? null,
    }
  })
}

/** Form 700 filing headers for an official, newest first. Separate from
 *  getEconomicInterests because a filing with zero interest line items
 *  ("no reportable interests declared") never appears in an interests-side
 *  join — and that absence is itself a Tier 1 fact the profile must show. */
export async function getForm700Filings(
  officialId: string
): Promise<Form700Filing[]> {
  const { data, error } = await supabase
    .from('form700_filings')
    .select(COLS_FORM700_FILING)
    .eq('official_id', officialId)
    .order('filing_year', { ascending: false })
    .order('period_start', { ascending: false, nullsFirst: false })

  if (error) {
    console.error('getForm700Filings query failed:', error)
    return []
  }

  return (data ?? []) as unknown as Form700Filing[]
}

export async function getOfficialWithStats(
  officialId: string,
  cityFips = RICHMOND_FIPS
) {
  const { data: official, error } = await supabase
    .from('officials')
    .select('*')
    .eq('id', officialId)
    .eq('city_fips', cityFips)
    .single()

  if (error || !official) return null

  // Vote and attendance totals are independent once the official is known.
  const [{ count: voteCount }, { data: attendance }] = await Promise.all([
    supabase
      .from('votes')
      .select('id', { count: 'exact', head: true })
      .eq('official_id', officialId),
    supabase
      .from('meeting_attendance')
      .select('status')
      .eq('official_id', officialId),
  ])

  const total = attendance?.length ?? 0
  const present = attendance?.filter((a) => a.status === 'present' || a.status === 'late').length ?? 0
  const attendanceRate = total > 0 ? present / total : 0

  return {
    ...(official as Official),
    vote_count: voteCount ?? 0,
    attendance_rate: attendanceRate,
    meetings_attended: present,
    meetings_total: total,
  }
}

export async function getOfficialCategoryBreakdown(
  officialId: string,
  cityFips = RICHMOND_FIPS
) {
  // Get all votes by this official, joined to agenda items for category
  const { data, error } = await supabase
    .from('votes')
    .select('id, motions!inner(agenda_items!inner(category))')
    .eq('official_id', officialId)

  if (error) {
    console.error('getOfficialCategoryBreakdown query failed:', error)
    return []
  }

  // Aggregate by category
  const categoryMap = new Map<string, number>()
  for (const vote of data ?? []) {
    const category = (
      (vote as Record<string, unknown>).motions as {
        agenda_items: { category: string | null }
      }
    )?.agenda_items?.category
    if (category) {
      categoryMap.set(category, (categoryMap.get(category) ?? 0) + 1)
    }
  }

  return Array.from(categoryMap.entries())
    .map(([category, count]) => ({ category, count }))
    .sort((a, b) => b.count - a.count)
}


// ─── Stats ───────────────────────────────────────────────────

export async function getMeetingStats(cityFips = RICHMOND_FIPS) {
  const [meetings, summaries, comments, topics, contributions, flags] = await Promise.all([
    supabase.from('meetings').select('meeting_date', { count: 'exact' }).eq('city_fips', cityFips),
    supabase.from('agenda_items').select('id', { count: 'exact', head: true }).is('agenda_source_retired_at', null).not('plain_language_summary', 'is', null),
    supabase.from('public_comments').select('id', { count: 'exact', head: true }),
    supabase.from('agenda_items').select('topic_label', { count: 'exact' }).is('agenda_source_retired_at', null).not('topic_label', 'is', null),
    supabase.from('contributions').select('id', { count: 'exact', head: true }).eq('city_fips', cityFips),
    supabase.from('conflict_flags').select('id', { count: 'exact', head: true }).eq('city_fips', cityFips).eq('is_current', true),
  ])

  // Compute years span from meeting dates
  const meetingDates = (meetings.data ?? []).map((m) => new Date(m.meeting_date).getFullYear())
  const minYear = Math.min(...(meetingDates.length > 0 ? meetingDates : [new Date().getFullYear()]))
  const maxYear = Math.max(...(meetingDates.length > 0 ? meetingDates : [new Date().getFullYear()]))
  const yearsOfMeetings = maxYear - minYear + 1

  // Count unique topic labels
  const topicLabels = new Set((topics.data ?? []).map((t) => t.topic_label))

  const stats = {
    meetings: meetings.count ?? 0,
    yearsOfMeetings,
    summaries: summaries.count ?? 0,
    publicComments: comments.count ?? 0,
    uniqueTopics: topicLabels.size,
    contributions: contributions.count ?? 0,
    conflictFlags: flags.count ?? 0,
  }

  if (stats.meetings === 0) {
    console.warn('[Richmond Commons] WARNING: getMeetingStats returned 0 meetings — possible Supabase connectivity issue during build/ISR')
  }

  return stats
}


// ─── Pattern Detection (S6) ─────────────────────────────────

/**
 * Parse vote_tally string into ayes and nays.
 * Handles multiple formats from extraction:
 *   "7-0"                              → { ayes: 7, nays: 0 }
 *   "7 to 0"                           → { ayes: 7, nays: 0 }
 *   "Ayes (6), Noes (1), Absent (0)"   → { ayes: 6, nays: 1 }
 *   "Ayes (7): Councilmember..."        → { ayes: 7, nays: 0 }
 *   "Ayes (7)"                          → { ayes: 7, nays: 0 }
 * Returns null if unparseable (e.g., "died for lack of a second").
 */
export function parseVoteTally(tally: string | null): { ayes: number; nays: number } | null {
  if (!tally) return null

  // Format: "7-0" or "5 - 2"
  const dashMatch = tally.match(/^(\d+)\s*-\s*(\d+)/)
  if (dashMatch) return { ayes: parseInt(dashMatch[1], 10), nays: parseInt(dashMatch[2], 10) }

  // Format: "7 to 0"
  const toMatch = tally.match(/^(\d+)\s+to\s+(\d+)/i)
  if (toMatch) return { ayes: parseInt(toMatch[1], 10), nays: parseInt(toMatch[2], 10) }

  // Format: "Ayes (N)" with optional "Noes (M)" / "Nays (M)"
  const ayesMatch = tally.match(/Ayes?\s*\((\d+)\)/i)
  if (ayesMatch) {
    const ayes = parseInt(ayesMatch[1], 10)
    const noesMatch = tally.match(/No(?:e|ay)s?\s*\((\d+)\)/i)
    const nays = noesMatch ? parseInt(noesMatch[1], 10) : 0
    return { ayes, nays }
  }

  // Format: "Ayes: [names]. Noes: [names]." — count comma-separated names
  const ayesNamesMatch = tally.match(/Ayes:\s*([^.]+)\./i)
  if (ayesNamesMatch) {
    const ayeNames = ayesNamesMatch[1].split(/,\s*(?:and\s+)?/).filter((n) => n.trim() && n.trim().toLowerCase() !== 'none')
    const noesNamesMatch = tally.match(/Noes:\s*([^.]+)\./i)
    const noeNames = noesNamesMatch
      ? noesNamesMatch[1].split(/,\s*(?:and\s+)?/).filter((n) => n.trim() && n.trim().toLowerCase() !== 'none')
      : []
    if (ayeNames.length > 0) return { ayes: ayeNames.length, nays: noeNames.length }
  }

  return null
}

// computeControversyScore formula moved to SQL RPCs (migration 038):
// split_vote_weight * 6 + comment_weight * 3 + multiple_motions * 1

/**
 * Get category-level statistics for council time-spent analysis.
 */
export async function getCategoryStats(
  cityFips = RICHMOND_FIPS
): Promise<CategoryStats[]> {
  // Server-side RPC: aggregation + joins happen in SQL (migration 038)
  // Replaces ~50 sequential PostgREST round-trips with a single query
  const { data, error } = await supabase
    .rpc('get_category_stats', { p_city_fips: cityFips })

  if (error) throw error

  return ((data ?? []) as Array<Record<string, unknown>>).map((row) => ({
    category: row.category as string,
    item_count: Number(row.item_count),
    vote_count: Number(row.vote_count),
    split_vote_count: Number(row.split_vote_count),
    unanimous_vote_count: Number(row.unanimous_vote_count),
    avg_controversy_score: Number(row.avg_controversy_score),
    max_controversy_score: Number(row.max_controversy_score),
    total_public_comments: Number(row.total_public_comments),
    percentage_of_agenda: Number(row.percentage_of_agenda),
  }))
}

/** Get all agenda items in a given category, with meeting context */
export async function getAgendaItemsByCategory(
  category: string,
  cityFips = RICHMOND_FIPS
) {
  const { data, error } = await supabase
    .from('agenda_items')
    .select(`
      id,
      meeting_id,
      item_number,
      title,
      description,
      category,
      is_consent_calendar,
      was_pulled_from_consent,
      summary_headline,
      plain_language_summary,
      financial_amount,
      meetings!inner (
        meeting_date,
        meeting_type
      )
    `)
    .is('agenda_source_retired_at', null)
    .eq('category', category)
    .eq('meetings.city_fips', cityFips)
    .order('meetings(meeting_date)', { ascending: false })

  if (error) {
    console.error('getAgendaItemsByCategory query failed:', error)
    return []
  }

  return (data ?? []).map((row) => {
    const meeting = row.meetings as unknown as { meeting_date: string; meeting_type: string }
    return {
      id: row.id as string,
      meeting_id: row.meeting_id as string,
      item_number: row.item_number as string,
      title: row.title as string,
      description: row.description as string | null,
      category: row.category as string | null,
      is_consent_calendar: row.is_consent_calendar as boolean,
      was_pulled_from_consent: row.was_pulled_from_consent as boolean,
      summary_headline: row.summary_headline as string | null,
      plain_language_summary: row.plain_language_summary as string | null,
      financial_amount: row.financial_amount as string | null,
      meeting_date: meeting.meeting_date,
      meeting_type: meeting.meeting_type,
    }
  })
}

/**
 * Get the most controversial agenda items across all meetings.
 */
export async function getControversialItems(
  limit = 20,
  cityFips = RICHMOND_FIPS
): Promise<ControversyItem[]> {
  // Server-side RPC: scoring + joins + per-meeting normalization in SQL (migration 038)
  const { data, error } = await supabase
    .rpc('get_controversial_items', { p_city_fips: cityFips, p_limit: limit })

  if (error) {
    console.error('getControversialItems RPC failed:', error)
    return []
  }

  return ((data ?? []) as Array<Record<string, unknown>>).map((row) => ({
    agenda_item_id: row.agenda_item_id as string,
    meeting_id: row.meeting_id as string,
    meeting_date: row.meeting_date as string,
    item_number: row.item_number as string,
    title: row.title as string,
    category: (row.category as string | null),
    controversy_score: Number(row.controversy_score),
    vote_tally: (row.vote_tally as string | null),
    result: row.result as string,
    public_comment_count: Number(row.public_comment_count),
    motion_count: Number(row.motion_count),
  }))
}


// ─── Most Discussed Items ────────────────────────────────────

export interface MostDiscussedItem {
  agenda_item_id: string
  meeting_id: string
  meeting_date: string
  title: string
  summary_headline: string | null
  topic_label: string | null
  public_comment_count: number
}

/**
 * Fetch agenda items with the highest public comment counts from recent meetings.
 * Used on the homepage to surface community engagement.
 */
export async function getMostDiscussedItems(
  limit = 2,
  daysBack = 90,
  cityFips = RICHMOND_FIPS,
): Promise<MostDiscussedItem[]> {
  const cutoff = new Date()
  cutoff.setDate(cutoff.getDate() - daysBack)
  const cutoffStr = cutoff.toISOString().split('T')[0]

  const { data, error } = await supabase
    .from('agenda_items')
    .select(`
      id,
      meeting_id,
      title,
      summary_headline,
      topic_label,
      public_comment_count,
      meetings!inner (
        meeting_date,
        city_fips
      )
    `)
    .is('agenda_source_retired_at', null)
    .eq('meetings.city_fips', cityFips)
    .gte('meetings.meeting_date', cutoffStr)
    .gt('public_comment_count', 1)
    .eq('is_consent_calendar', false)
    .order('public_comment_count', { ascending: false })
    .limit(limit)

  if (error) {
    console.error('getMostDiscussedItems query failed:', error)
    return []
  }

  return ((data ?? []) as Array<Record<string, unknown>>).map((row) => {
    const meeting = row.meetings as unknown as { meeting_date: string }
    return {
      agenda_item_id: row.id as string,
      meeting_id: row.meeting_id as string,
      meeting_date: meeting.meeting_date,
      title: row.title as string,
      summary_headline: row.summary_headline as string | null,
      topic_label: row.topic_label as string | null,
      public_comment_count: Number(row.public_comment_count),
    }
  })
}


// ─── Coalition / Voting Alignment (S6.1) ────────────────────

/**
 * Fetch contested votes for a city using server-side RPC.
 * The database function handles joins and filters to contested motions
 * (motions with both aye and nay votes) entirely in SQL — avoiding
 * PostgREST's row limits and triple-nested join overhead.
 */
interface ContestedVoteRow {
  motion_id: string
  official_id: string
  official_name: string
  vote_choice: string
  category: string | null
}

async function fetchVotesForAlignment(
  cityFips = RICHMOND_FIPS,
  officialIds?: string[],
): Promise<ContestedVoteRow[]> {
  // Push the current-council filter into SQL so the RPC returns ~hundreds of
  // rows instead of ~10K. Migration 103 added p_official_ids; without that
  // filter, the response can hit PostgREST's 10K-row cap and the slow path
  // can hit the anon role's statement_timeout under load.
  const { data: votes, error } = await supabase
    .rpc('get_contested_votes', {
      p_city_fips: cityFips,
      p_official_ids: officialIds ?? null,
    })

  if (error) {
    throw new Error(`Coalition data fetch failed: ${error.message}`)
  }

  return (votes ?? []) as ContestedVoteRow[]
}

/**
 * Compute pairwise alignment between council members.
 * By default, shows only the current council (is_current=true, council roles).
 * Returns overall alignment and per-category breakdowns.
 */
export async function getCoalitionData(cityFips = RICHMOND_FIPS): Promise<{
  alignments: PairwiseAlignment[]
  divergences: CategoryDivergence[]
  officials: Array<{ id: string; name: string }>
}> {
  // Fetch current council members to filter results
  const { data: currentOfficials } = await supabase
    .from('officials')
    .select('id, name')
    .eq('city_fips', cityFips)
    .eq('is_current', true)
    .in('role', COUNCIL_ROLES)

  const currentIdsArr = (currentOfficials ?? []).map((o) => o.id as string)

  // Pass the current-council IDs into the RPC so filtering and re-evaluation
  // of contestedness happen in SQL (migration 103). The previous client-side
  // path fetched ~10K rows and was vulnerable to PostgREST's 10K row cap and
  // the anon statement_timeout.
  const votes = await fetchVotesForAlignment(cityFips, currentIdsArr)

  const votesByMotion = new Map<string, Array<{
    official_id: string
    official_name: string
    vote_choice: string
    category: string | null
  }>>()

  for (const v of votes) {
    const entry = votesByMotion.get(v.motion_id) ?? []
    entry.push({
      official_id: v.official_id,
      official_name: v.official_name,
      vote_choice: v.vote_choice,
      category: v.category,
    })
    votesByMotion.set(v.motion_id, entry)
  }

  // Collect unique officials from filtered votes (should be current council only)
  const officialMap = new Map<string, string>()
  for (const [, motionVotes] of votesByMotion) {
    for (const v of motionVotes) {
      officialMap.set(v.official_id, v.official_name)
    }
  }
  const officials = Array.from(officialMap.entries())
    .map(([id, name]) => ({ id, name }))
    .sort((a, b) => a.name.localeCompare(b.name))

  // Compute pairwise alignment: for each motion, compare all pairs of voters
  // Key: "officialA_id|officialB_id|category" -> { agree, disagree }
  const pairStats = new Map<string, { agree: number; disagree: number }>()

  const makePairKey = (idA: string, idB: string, category: string | null) => {
    const [first, second] = idA < idB ? [idA, idB] : [idB, idA]
    return `${first}|${second}|${category ?? '__overall__'}`
  }

  for (const [, motionVotes] of votesByMotion) {
    // For each pair of voters on this motion
    for (let i = 0; i < motionVotes.length; i++) {
      for (let j = i + 1; j < motionVotes.length; j++) {
        const a = motionVotes[i]
        const b = motionVotes[j]
        const agreed = a.vote_choice === b.vote_choice

        // Overall
        const overallKey = makePairKey(a.official_id, b.official_id, null)
        const overallEntry = pairStats.get(overallKey) ?? { agree: 0, disagree: 0 }
        if (agreed) overallEntry.agree++
        else overallEntry.disagree++
        pairStats.set(overallKey, overallEntry)

        // Per-category
        if (a.category) {
          const catKey = makePairKey(a.official_id, b.official_id, a.category)
          const catEntry = pairStats.get(catKey) ?? { agree: 0, disagree: 0 }
          if (agreed) catEntry.agree++
          else catEntry.disagree++
          pairStats.set(catKey, catEntry)
        }
      }
    }
  }

  // Build alignment results
  const alignments: PairwiseAlignment[] = []
  for (const [key, stats] of pairStats) {
    const [idA, idB, cat] = key.split('|')
    const total = stats.agree + stats.disagree
    alignments.push({
      official_a_id: idA,
      official_a_name: officialMap.get(idA) ?? idA,
      official_b_id: idB,
      official_b_name: officialMap.get(idB) ?? idB,
      category: cat === '__overall__' ? null : cat,
      agreement_count: stats.agree,
      disagreement_count: stats.disagree,
      total_shared_votes: total,
      agreement_rate: total > 0 ? Math.round((stats.agree / total) * 1000) / 1000 : 0,
    })
  }

  // Compute category divergences: pairs where category alignment differs significantly from overall
  const divergences = computeDivergences(alignments)

  return { alignments, divergences, officials }
}

const MIN_SHARED_VOTES = 5

/**
 * Find category-level divergences: pairs that agree overall but diverge on a specific category.
 */
function computeDivergences(alignments: PairwiseAlignment[]): CategoryDivergence[] {
  const overallMap = new Map<string, PairwiseAlignment>()
  const categoryAlignments: PairwiseAlignment[] = []

  for (const a of alignments) {
    const pairKey = `${a.official_a_id}|${a.official_b_id}`
    if (a.category === null) {
      overallMap.set(pairKey, a)
    } else {
      categoryAlignments.push(a)
    }
  }

  const divergences: CategoryDivergence[] = []
  for (const catAlignment of categoryAlignments) {
    if (catAlignment.total_shared_votes < MIN_SHARED_VOTES) continue

    const pairKey = `${catAlignment.official_a_id}|${catAlignment.official_b_id}`
    const overall = overallMap.get(pairKey)
    if (!overall) continue

    const gap = overall.agreement_rate - catAlignment.agreement_rate
    if (gap > 0.15) {
      divergences.push({
        official_a_id: catAlignment.official_a_id,
        official_a_name: catAlignment.official_a_name,
        official_b_id: catAlignment.official_b_id,
        official_b_name: catAlignment.official_b_name,
        overall_agreement_rate: overall.agreement_rate,
        category: catAlignment.category as string,
        category_agreement_rate: catAlignment.agreement_rate,
        divergence_gap: Math.round(gap * 1000) / 1000,
        shared_category_votes: catAlignment.total_shared_votes,
      })
    }
  }

  return divergences.sort((a, b) => b.divergence_gap - a.divergence_gap)
}

/**
 * Per-motion vote breakdowns for the public voting-patterns page.
 * Returns one entry per contested motion, with each current member's vote.
 *
 * Filters to current council members only (matching getCoalitionData) so the
 * table columns stay stable. Members not present on a motion show as 'absent'.
 *
 * Sorted newest-first so recent splits surface at the top.
 */
export async function getDivergentMotions(cityFips = RICHMOND_FIPS): Promise<{
  motions: DivergentMotion[]
  officials: Array<{ id: string; name: string }>
}> {
  const { data: currentOfficials } = await supabase
    .from('officials')
    .select('id, name')
    .eq('city_fips', cityFips)
    .eq('is_current', true)
    .in('role', COUNCIL_ROLES)
    .order('name')

  const officials = (currentOfficials ?? []).map((o) => ({ id: o.id as string, name: o.name as string }))
  const currentIdsArr = officials.map((o) => o.id)

  // Push the current-council filter into SQL (migration 103). The RPC
  // pre-filters rows to these officials AND re-evaluates contestedness within
  // that subset, so the response stays well under PostgREST's 10K row cap.
  const { data: rows, error } = await supabase
    .rpc('get_divergent_motions_detail', {
      p_city_fips: cityFips,
      p_official_ids: currentIdsArr,
    })

  if (error) {
    throw new Error(`Divergent motions fetch failed: ${error.message}`)
  }

  const typedRows = (rows ?? []) as DivergentMotionRow[]

  const motionMap = new Map<string, DivergentMotion>()
  for (const row of typedRows) {
    let motion = motionMap.get(row.motion_id)
    if (!motion) {
      motion = {
        motion_id: row.motion_id,
        motion_text: row.motion_text,
        motion_result: row.motion_result,
        vote_tally: row.vote_tally,
        meeting_id: row.meeting_id,
        meeting_date: row.meeting_date,
        agenda_item_id: row.agenda_item_id,
        agenda_item_title: row.agenda_item_title,
        agenda_item_number: row.agenda_item_number,
        category: row.category,
        topic_label: row.topic_label,
        is_procedural: row.is_procedural,
        votes: {},
      }
      motionMap.set(row.motion_id, motion)
    }
    motion.votes[row.official_id] = row.vote_choice
  }

  const motions: DivergentMotion[] = []
  for (const motion of motionMap.values()) {
    // Default 'absent' for current members not in the votes map
    for (const o of officials) {
      if (!(o.id in motion.votes)) motion.votes[o.id] = 'absent'
    }
    motions.push(motion)
  }

  motions.sort((a, b) => b.meeting_date.localeCompare(a.meeting_date))

  return { motions, officials }
}

// ─── Cross-Meeting Patterns (S6.2) ──────────────────────────

/**
 * Get cross-meeting pattern data: donor-category concentration and cross-official overlap.
 * Crosses financial data (contributions) with legislative data (votes by category).
 */
export async function getCrossMeetingPatterns(cityFips = RICHMOND_FIPS): Promise<{
  donorPatterns: DonorCategoryPattern[]
  donorOverlaps: DonorOverlap[]
  summaryStats: {
    totalDonors: number
    concentratedDonors: number
    multiRecipientDonors: number
    totalContributions: number
  }
}> {
  // 1. Get current council members, then their committees.
  // Filter by both is_current and council roles to exclude former members
  // who may still be marked current, and non-council officials.
  const { data: currentOfficials } = await supabase
    .from('officials')
    .select('id')
    .eq('city_fips', cityFips)
    .eq('is_current', true)
    .in('role', COUNCIL_ROLES)

  const currentOfficialIds = (currentOfficials ?? []).map((o) => o.id)
  if (currentOfficialIds.length === 0) {
    return { donorPatterns: [], donorOverlaps: [], summaryStats: { totalDonors: 0, concentratedDonors: 0, multiRecipientDonors: 0, totalContributions: 0 } }
  }

  const { data: committees } = await supabase
    .from('committees')
    .select('id, official_id, candidate_name')
    .eq('city_fips', cityFips)
    .in('official_id', currentOfficialIds)

  if (!committees || committees.length === 0) {
    return { donorPatterns: [], donorOverlaps: [], summaryStats: { totalDonors: 0, concentratedDonors: 0, multiRecipientDonors: 0, totalContributions: 0 } }
  }

  const committeeIds = committees.map((c) => c.id)
  const committeeToOfficial = new Map<string, string>()
  const committeeToName = new Map<string, string>()
  for (const c of committees) {
    committeeToOfficial.set(c.id, c.official_id as string)
    committeeToName.set(c.id, c.candidate_name as string ?? 'Unknown')
  }

  // 2. Get all contributions to these committees with donor info
  const { data: contributions, error: contribError } = await supabase
    .from('contributions')
    .select('id, amount, committee_id, donor_id, donors!inner(id, name, employer, donor_pattern)')
    .in('committee_id', committeeIds)
    .eq('city_fips', cityFips)

  if (contribError) throw contribError
  if (!contributions || contributions.length === 0) {
    return { donorPatterns: [], donorOverlaps: [], summaryStats: { totalDonors: 0, concentratedDonors: 0, multiRecipientDonors: 0, totalContributions: 0 } }
  }

  // 3. Get official names
  const officialIds = Array.from(new Set(committees.map((c) => c.official_id as string)))
  const { data: officials } = await supabase
    .from('officials')
    .select('id, name')
    .in('id', officialIds)

  const officialNameMap = new Map<string, string>()
  for (const o of officials ?? []) {
    officialNameMap.set(o.id, o.name)
  }

  // 4. Get votes by official with category (reuse existing pattern)
  const { data: meetings } = await supabase
    .from('meetings')
    .select('id')
    .eq('city_fips', cityFips)

  const meetingIds = (meetings ?? []).map((m) => m.id)

  const { data: votes } = await supabase
    .from('votes')
    .select(`
      official_id,
      motions!inner (
        agenda_items!inner (
          meeting_id,
          category
        )
      )
    `)
    .not('official_id', 'is', null)
    .in('vote_choice', ['aye', 'nay'])

  // Build: official_id -> category vote counts
  const meetingIdSet = new Set(meetingIds)
  const officialCategoryVotes = new Map<string, Map<string, number>>()
  for (const v of votes ?? []) {
    const motion = v.motions as unknown as { agenda_items: { meeting_id: string; category: string | null } }
    if (!meetingIdSet.has(motion.agenda_items.meeting_id)) continue
    const cat = motion.agenda_items.category ?? 'other'
    const officialId = v.official_id as string

    const catMap = officialCategoryVotes.get(officialId) ?? new Map<string, number>()
    catMap.set(cat, (catMap.get(cat) ?? 0) + 1)
    officialCategoryVotes.set(officialId, catMap)
  }

  // 5. Build donor aggregation
  type DonorAgg = {
    id: string
    name: string
    employer: string | null
    pattern: string | null
    totalAmount: number
    recipients: Map<string, { officialId: string; officialName: string; amount: number; count: number }>
  }

  const donorAgg = new Map<string, DonorAgg>()

  for (const c of contributions) {
    const donor = c.donors as unknown as { id: string; name: string; employer: string | null; donor_pattern: string | null }
    const officialId = committeeToOfficial.get(c.committee_id as string)
    if (!officialId) continue

    // Skip government entities that appear as "donors" in filing data
    const donorNameLower = donor.name.toLowerCase()
    if (/^(the )?(city|county|state|town) of\b/.test(donorNameLower)) continue

    // Key by name (not id) to merge same-person entries with different employers
    const agg = donorAgg.get(donor.name) ?? {
      id: donor.id,
      name: donor.name,
      employer: donor.employer,
      pattern: donor.donor_pattern,
      totalAmount: 0,
      recipients: new Map(),
    }

    agg.totalAmount += c.amount as number
    // Prefer non-null employer (latest filing wins for display)
    if (donor.employer) agg.employer = donor.employer

    const existing = agg.recipients.get(officialId)
    if (existing) {
      existing.amount += c.amount as number
      existing.count += 1
    } else {
      agg.recipients.set(officialId, {
        officialId,
        officialName: officialNameMap.get(officialId) ?? committeeToName.get(c.committee_id as string) ?? 'Unknown',
        amount: c.amount as number,
        count: 1,
      })
    }

    donorAgg.set(donor.name, agg)
  }

  // 6. Compute donor-category concentration
  const donorPatterns: DonorCategoryPattern[] = []
  for (const [, agg] of donorAgg) {
    // Aggregate category votes across all recipients of this donor
    const categoryCounts = new Map<string, number>()
    let totalVoteCount = 0

    for (const [officialId] of agg.recipients) {
      const catMap = officialCategoryVotes.get(officialId)
      if (!catMap) continue
      for (const [cat, count] of catMap) {
        categoryCounts.set(cat, (categoryCounts.get(cat) ?? 0) + count)
        totalVoteCount += count
      }
    }

    if (totalVoteCount === 0) continue

    const breakdown = Array.from(categoryCounts.entries())
      .map(([category, vote_count]) => ({ category, vote_count }))
      .sort((a, b) => b.vote_count - a.vote_count)

    const topCategory = breakdown[0]?.category ?? 'other'
    const maxCategoryCount = breakdown[0]?.vote_count ?? 0
    const concentration = totalVoteCount > 0 ? maxCategoryCount / totalVoteCount : 0

    // Only include donors with > $1,000 total and concentration > 0.3
    if (agg.totalAmount >= 1000 && concentration >= 0.3) {
      donorPatterns.push({
        donor_id: agg.id,
        donor_name: agg.name,
        donor_employer: agg.employer,
        donor_pattern: agg.pattern,
        total_contributed: Math.round(agg.totalAmount * 100) / 100,
        recipient_count: agg.recipients.size,
        top_category: topCategory,
        category_concentration: Math.round(concentration * 1000) / 1000,
        category_breakdown: breakdown.slice(0, 5),
      })
    }
  }

  donorPatterns.sort((a, b) => b.category_concentration - a.category_concentration)

  // 7. Compute cross-official donor overlap (donors contributing to 2+ officials)
  const donorOverlaps: DonorOverlap[] = []
  for (const [, agg] of donorAgg) {
    if (agg.recipients.size < 2) continue

    donorOverlaps.push({
      donor_id: agg.id,
      donor_name: agg.name,
      donor_employer: agg.employer,
      total_contributed: Math.round(agg.totalAmount * 100) / 100,
      recipients: Array.from(agg.recipients.values())
        .map((r) => ({
          official_id: r.officialId,
          official_name: r.officialName,
          amount: Math.round(r.amount * 100) / 100,
          contribution_count: r.count,
        }))
        .sort((a, b) => b.amount - a.amount),
    })
  }

  donorOverlaps.sort((a, b) => b.recipients.length - a.recipients.length || b.total_contributed - a.total_contributed)

  return {
    donorPatterns: donorPatterns.slice(0, 50),
    donorOverlaps: donorOverlaps.slice(0, 50),
    summaryStats: {
      totalDonors: donorAgg.size,
      concentratedDonors: donorPatterns.length,
      multiRecipientDonors: donorOverlaps.length,
      totalContributions: contributions.length,
    },
  }
}


// ─── Comparative Stats (S14-E4) ─────────────────────────────

export interface OfficialComparativeStats {
  official_id: string
  unique_donor_count: number
  total_contributions: number
  donor_count_rank: number          // 1 = most donors
  contributions_rank: number        // 1 = highest total
  total_officials: number           // typically 7
}

export async function getOfficialComparativeStats(
  officialId: string,
  cityFips = RICHMOND_FIPS
): Promise<OfficialComparativeStats | null> {
  // Step 1: Get all committees linked to officials in this city
  const { data: committees, error: committeeError } = await supabase
    .from('committees')
    .select('id, official_id, officials!inner(is_current, role)')
    .eq('city_fips', cityFips)
    .eq('officials.is_current', true)
    .in('officials.role', COUNCIL_ROLES)

  if (committeeError || !committees || committees.length === 0) {
    console.error('getOfficialComparativeStats committees query failed:', committeeError)
    return null
  }

  // Build a map: official_id -> committee_ids
  const officialCommittees = new Map<string, string[]>()
  for (const c of committees) {
    const oid = c.official_id as string
    const existing = officialCommittees.get(oid) ?? []
    existing.push(c.id as string)
    officialCommittees.set(oid, existing)
  }

  // Step 2: For each official, fetch contribution stats
  interface OfficialAgg {
    official_id: string
    unique_donor_count: number
    total_contributions: number
  }

  const allOfficialIds = Array.from(officialCommittees.keys())
  const allCommitteeIds = committees.map((c) => c.id as string)

  // Fetch all contributions for all official committees in one query
  const { data: contributions, error: contribError } = await supabase
    .from('contributions')
    .select('committee_id, donor_id, amount')
    .in('committee_id', allCommitteeIds)
    .eq('city_fips', cityFips)

  if (contribError) {
    console.error('getOfficialComparativeStats contributions query failed:', contribError)
    return null
  }

  // Aggregate per official
  const officialStats = new Map<string, { donors: Set<string>; total: number }>()
  for (const oid of allOfficialIds) {
    officialStats.set(oid, { donors: new Set(), total: 0 })
  }

  for (const row of contributions ?? []) {
    const committeeId = row.committee_id as string
    // Find which official owns this committee
    for (const [oid, cids] of officialCommittees.entries()) {
      if (cids.includes(committeeId)) {
        const stats = officialStats.get(oid)
        if (stats) {
          stats.donors.add(row.donor_id as string)
          stats.total += row.amount as number
        }
        break
      }
    }
  }

  // Step 3: Build ranked list
  const aggregates: OfficialAgg[] = allOfficialIds.map((oid) => {
    const stats = officialStats.get(oid)!
    return {
      official_id: oid,
      unique_donor_count: stats.donors.size,
      total_contributions: stats.total,
    }
  })

  // Sort by donor count descending for ranking
  const byDonors = [...aggregates].sort((a, b) => b.unique_donor_count - a.unique_donor_count)
  const byContributions = [...aggregates].sort((a, b) => b.total_contributions - a.total_contributions)

  const target = aggregates.find((a) => a.official_id === officialId)
  if (!target) return null

  const donorRank = byDonors.findIndex((a) => a.official_id === officialId) + 1
  const contribRank = byContributions.findIndex((a) => a.official_id === officialId) + 1

  return {
    official_id: officialId,
    unique_donor_count: target.unique_donor_count,
    total_contributions: target.total_contributions,
    donor_count_rank: donorRank,
    contributions_rank: contribRank,
    total_officials: allOfficialIds.length,
  }
}


export interface CycleFundraisingStats {
  allTime: { total: number; donors: number }
  lastElection: { total: number; donors: number; label: string }
  sinceLastElection: { total: number; donors: number }
}

/** Bulk fundraising stats per election cycle for council listing cards */
export async function getBulkFundraisingStats(
  cityFips = RICHMOND_FIPS,
): Promise<Map<string, CycleFundraisingStats>> {
  const result = new Map<string, CycleFundraisingStats>()

  // Get election dates to define cycles
  const electionDates = await getPastElectionDates(cityFips)

  const { data: committees } = await supabase
    .from('committees')
    .select('id, official_id')
    .eq('city_fips', cityFips)
    .not('official_id', 'is', null)

  if (!committees || committees.length === 0) return result

  const officialCommittees = new Map<string, string[]>()
  for (const c of committees) {
    const oid = c.official_id as string
    const existing = officialCommittees.get(oid) ?? []
    existing.push(c.id as string)
    officialCommittees.set(oid, existing)
  }

  const allCommitteeIds = committees.map((c) => c.id as string)
  const { data: contributions } = await supabase
    .from('contributions')
    .select('committee_id, donor_id, amount, contribution_date')
    .in('committee_id', allCommitteeIds)
    .eq('city_fips', cityFips)

  // Define cycle boundaries
  const lastElection = electionDates.length > 0 ? electionDates[electionDates.length - 1] : null
  const prevElection = electionDates.length > 1 ? electionDates[electionDates.length - 2] : null
  const lastElectionYear = lastElection ? new Date(lastElection + 'T00:00:00').getFullYear().toString() : ''

  for (const [officialId, cids] of officialCommittees.entries()) {
    const officialContribs = (contributions ?? []).filter(
      (c) => cids.includes(c.committee_id as string)
    )

    // Last election cycle: prevElection < date <= lastElection
    const lastCycle = lastElection
      ? officialContribs.filter((c) => {
          const d = c.contribution_date as string
          if (prevElection && d <= prevElection) return false
          return d <= lastElection
        })
      : []

    // Since last election: date > lastElection
    const sinceLast = lastElection
      ? officialContribs.filter((c) => (c.contribution_date as string) > lastElection)
      : officialContribs

    result.set(officialId, {
      allTime: {
        total: officialContribs.reduce((s, c) => s + (c.amount as number), 0),
        donors: new Set(officialContribs.map((c) => c.donor_id as string)).size,
      },
      lastElection: {
        total: lastCycle.reduce((s, c) => s + (c.amount as number), 0),
        donors: new Set(lastCycle.map((c) => c.donor_id as string)).size,
        label: lastElectionYear ? `${lastElectionYear} Election` : '',
      },
      sinceLastElection: {
        total: sinceLast.reduce((s, c) => s + (c.amount as number), 0),
        donors: new Set(sinceLast.map((c) => c.donor_id as string)).size,
      },
    })
  }

  return result
}


// ─── Computed Alignment (fallback when bio_factual is null) ───────────────

export async function computeAlignmentStats(officialId: string): Promise<{
  majority_alignment_rate: number | null
  sole_dissent_count: number
}> {
  // Fetch all votes for this official with their motion's other votes
  const { data: votes, error } = await supabase
    .from('votes')
    .select('motion_id, vote_choice')
    .eq('official_id', officialId)
    .neq('vote_choice', 'absent')

  if (error || !votes || votes.length === 0) {
    return { majority_alignment_rate: null, sole_dissent_count: 0 }
  }

  // Get all motion IDs this official voted on
  const motionIds = [...new Set(votes.map((v) => v.motion_id as string))]

  // Fetch all votes on these motions
  const { data: allVotes } = await supabase
    .from('votes')
    .select('motion_id, official_id, vote_choice')
    .in('motion_id', motionIds)
    .neq('vote_choice', 'absent')

  if (!allVotes) return { majority_alignment_rate: null, sole_dissent_count: 0 }

  // Group by motion
  const votesByMotion = new Map<string, Array<{ official_id: string; vote_choice: string }>>()
  for (const v of allVotes) {
    const mid = v.motion_id as string
    const list = votesByMotion.get(mid) ?? []
    list.push({ official_id: v.official_id as string, vote_choice: v.vote_choice as string })
    votesByMotion.set(mid, list)
  }

  let withMajority = 0
  let total = 0
  let soleDissents = 0

  for (const v of votes) {
    const mid = v.motion_id as string
    const motionVotes = votesByMotion.get(mid) ?? []
    if (motionVotes.length < 2) continue

    const officialChoice = v.vote_choice as string
    const ayes = motionVotes.filter((mv) => mv.vote_choice === 'aye').length
    const nays = motionVotes.filter((mv) => mv.vote_choice === 'nay').length
    const majority = ayes >= nays ? 'aye' : 'nay'

    total++
    if (officialChoice === majority) withMajority++

    // Sole dissent: this official's choice is unique
    const sameChoice = motionVotes.filter((mv) => mv.vote_choice === officialChoice).length
    if (sameChoice === 1 && motionVotes.length > 2) soleDissents++
  }

  return {
    majority_alignment_rate: total > 0 ? withMajority / total : null,
    sole_dissent_count: soleDissents,
  }
}

