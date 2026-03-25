import { supabase } from './supabase'
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
  VotingBloc,
  CategoryDivergence,
  DonorCategoryPattern,
  DonorOverlap,
  CategoryCount,
  TopicLabelCount,
  MeetingWithCounts,
  FinancialConnectionFlag,
  OfficialConnectionSummary,
  SearchResult,
  SearchResultType,
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
  PublicCommentDetail,
  AgendaItemDetail,
  AgendaItemRef,
  AgendaItemSibling,
  RelatedTopicItem,
} from './types'
import { CONFIDENCE_PUBLISHED } from './thresholds'

const RICHMOND_FIPS = '0660620'

/**
 * Warn when a query that should always return data comes back empty.
 * Logs to stderr so it shows up in Vercel build/function logs.
 * Helps diagnose ISR cache poisoning from transient Supabase outages.
 */
function warnIfEmpty(label: string, rows: unknown[] | null) {
  if (!rows || rows.length === 0) {
    console.warn(`[Richmond Common] WARNING: "${label}" returned 0 rows — possible Supabase connectivity issue during build/ISR`)
  }
}

/** Compute URL slug from official name (officials table has no slug column) */
function nameToSlug(name: string): string {
  return name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '')
}

/** Check if a name looks like a government entity (mirrors scanner's _is_government_entity) */
function isGovernmentEntity(name: string): boolean {
  const norm = name.toLowerCase().trim()
  if (!norm) return false
  const prefixes = ['city of', 'city and county', 'city &', 'county of', 'state of', 'town of', 'district of', 'village of', 'borough of']
  const suffixes = [' county', ' city', ' state', ' department']
  return prefixes.some(p => norm.startsWith(p)) || suffixes.some(s => norm.endsWith(s))
}

/** Filter out conflict flags where the matched entity is a government entity.
 *  Two cases:
 *  1. donor_vendor_expenditure flags where the vendor is a government entity
 *  2. campaign_contribution/temporal_correlation flags where the match was
 *     employer-based (match_type starts with "employer_to_") and the employer
 *     is a government entity — e.g., "city of richmond" as employer matches
 *     every agenda item. The scanner now prevents these, but stale DB flags remain.
 *  Works on any array with evidence/flag_type. */
function filterGovernmentEntityFlags<T extends { flag_type: string; evidence: Record<string, unknown>[] }>(flags: T[]): T[] {
  return flags.filter(f => {
    const ev = f.evidence?.[0]
    if (!ev) return true

    // Case 1: donor_vendor_expenditure with government entity vendor
    if (f.flag_type === 'donor_vendor_expenditure') {
      const vendor = ev.vendor
      if (typeof vendor === 'string' && isGovernmentEntity(vendor)) return false
    }

    // Case 2: employer-matched flags with government entity employer
    const matchType = ev.match_type
    if (typeof matchType === 'string' && matchType.startsWith('employer_to_')) {
      const employer = ev.donor_employer
      if (typeof employer === 'string' && isGovernmentEntity(employer)) return false
    }

    return true
  })
}

// ─── Meetings ────────────────────────────────────────────────

export async function getMeetings(cityFips = RICHMOND_FIPS) {
  const { data, error } = await supabase
    .from('meetings')
    .select('*')
    .eq('city_fips', cityFips)
    .order('meeting_date', { ascending: false })

  if (error) {
    console.error('getMeetings query failed:', error)
    return [] as Meeting[]
  }
  warnIfEmpty('getMeetings', data)
  return data as Meeting[]
}

export async function getMeetingsWithCounts(cityFips = RICHMOND_FIPS) {
  // Fetch meetings and server-side aggregated counts in parallel.
  // The RPC does all counting/grouping in PostgreSQL, eliminating
  // the client-side row-fetching pattern that hit Supabase max_rows limits.
  const [meetings, { data: counts, error: rpcError }] = await Promise.all([
    getMeetings(cityFips),
    supabase.rpc('get_meeting_counts', { p_city_fips: cityFips }),
  ])

  if (rpcError) {
    console.error('get_meeting_counts RPC failed:', rpcError)
  }

  interface MeetingCounts {
    meeting_id: string
    agenda_item_count: number
    vote_count: number
    categories: CategoryCount[]
    topic_labels: TopicLabelCount[]
  }

  const countMap = new Map(
    ((counts ?? []) as MeetingCounts[]).map((c) => [c.meeting_id, c])
  )

  return meetings.map((m) => {
    const c = countMap.get(m.id)
    const allCats = c?.categories ?? []
    const allLabels = c?.topic_labels ?? []
    return {
      ...m,
      agenda_item_count: Number(c?.agenda_item_count ?? 0),
      vote_count: Number(c?.vote_count ?? 0),
      top_categories: allCats.slice(0, 4),
      all_categories: allCats,
      top_topic_labels: allLabels.slice(0, 5),
      all_topic_labels: allLabels,
    }
  })
}

export async function getMeeting(meetingId: string): Promise<MeetingDetail | null> {
  // Fetch meeting
  const { data: meeting, error } = await supabase
    .from('meetings')
    .select('*')
    .eq('id', meetingId)
    .single()

  if (error || !meeting) return null

  // Fetch agenda items
  const { data: items } = await supabase
    .from('agenda_items')
    .select('*')
    .eq('meeting_id', meetingId)
    .order('item_number')

  // Fetch motions for all items
  const itemIds = (items ?? []).map((i) => i.id)
  const { data: motions } = await supabase
    .from('motions')
    .select('*')
    .in('agenda_item_id', itemIds.length > 0 ? itemIds : ['__none__'])
    .order('sequence_number')

  // Fetch votes for all motions
  const motionIds = (motions ?? []).map((m) => m.id)
  const { data: votes } = await supabase
    .from('votes')
    .select('*')
    .in('motion_id', motionIds.length > 0 ? motionIds : ['__none__'])

  // Fetch attendance with official info
  const { data: attendance } = await supabase
    .from('meeting_attendance')
    .select('*, officials(name, role)')
    .eq('meeting_id', meetingId)

  // Fetch closed session items
  const { data: closedSession } = await supabase
    .from('closed_session_items')
    .select('*')
    .eq('meeting_id', meetingId)

  // Fetch public comments with speaker names for summary
  const { data: commentRows } = await supabase
    .from('public_comments')
    .select('agenda_item_id, speaker_name')
    .eq('meeting_id', meetingId)

  // Fetch all officials for notable speaker detection
  const allOfficials = await getOfficials(meeting.city_fips as string)
  const officialNameMap = new Map(
    allOfficials.map((o) => [o.name.toLowerCase(), o])
  )

  // Build per-item comment counts and summaries
  const commentCountByItem = new Map<string, number>()
  const commentSpeakersByItem = new Map<string, string[]>()
  let totalPublicComments = 0
  for (const c of (commentRows ?? [])) {
    if (c.agenda_item_id) {
      const itemId = c.agenda_item_id as string
      commentCountByItem.set(itemId, (commentCountByItem.get(itemId) ?? 0) + 1)
      const speakers = commentSpeakersByItem.get(itemId) ?? []
      if (c.speaker_name) speakers.push(c.speaker_name as string)
      commentSpeakersByItem.set(itemId, speakers)
    }
    totalPublicComments++
  }

  // Assemble the nested structure
  const votesByMotion = new Map<string, Vote[]>()
  for (const v of (votes ?? []) as Vote[]) {
    const arr = votesByMotion.get(v.motion_id) ?? []
    arr.push(v)
    votesByMotion.set(v.motion_id, arr)
  }

  const motionsByItem = new Map<string, MotionWithVotes[]>()
  for (const m of (motions ?? []) as Motion[]) {
    const arr = motionsByItem.get(m.agenda_item_id) ?? []
    arr.push({ ...m, votes: votesByMotion.get(m.id) ?? [] })
    motionsByItem.set(m.agenda_item_id, arr)
  }

  const agendaItems: AgendaItemWithMotions[] = ((items ?? []) as AgendaItem[]).map((i) => {
    const count = commentCountByItem.get(i.id) ?? 0
    const speakers = commentSpeakersByItem.get(i.id) ?? []

    // Detect notable speakers (current/former officials)
    const notable: NotableSpeaker[] = []
    for (const name of speakers) {
      const official = officialNameMap.get(name.toLowerCase())
      if (official) {
        const role = official.is_current
          ? official.role.replace(/_/g, ' ')
          : `former ${official.role.replace(/_/g, ' ')}`
        // Deduplicate
        if (!notable.some(n => n.name === official.name)) {
          notable.push({ name: official.name, role })
        }
      }
    }

    return {
      ...i,
      motions: motionsByItem.get(i.id) ?? [],
      public_comment_count: count,
      comment_summary: count > 0 ? { total: count, notable_speakers: notable } : undefined,
    }
  })

  const attendanceWithOfficials = (attendance ?? []).map((a) => {
    const official = (a as Record<string, unknown>).officials as { name: string; role: string } | null
    return {
      id: a.id as string,
      meeting_id: a.meeting_id as string,
      official_id: a.official_id as string,
      status: a.status as MeetingAttendance['status'],
      notes: a.notes as string | null,
      official: official ?? { name: 'Unknown', role: 'unknown' },
    }
  })

  return {
    ...(meeting as Meeting),
    agenda_items: agendaItems,
    attendance: attendanceWithOfficials,
    closed_session_items: (closedSession ?? []) as ClosedSessionItem[],
    total_public_comments: totalPublicComments,
  }
}

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

export async function getOfficials(
  cityFips = RICHMOND_FIPS,
  opts: { currentOnly?: boolean; councilOnly?: boolean } = {},
) {
  let query = supabase
    .from('officials')
    .select('*')
    .eq('city_fips', cityFips)
    .order('name')

  if (opts.currentOnly) {
    query = query.eq('is_current', true)
  }
  if (opts.councilOnly) {
    query = query.in('role', COUNCIL_ROLES)
  }

  const { data, error } = await query
  if (error) {
    console.error('getOfficials query failed:', error)
    return [] as Official[]
  }
  warnIfEmpty('getOfficials', data)
  return deduplicateOfficials(data as Official[])
}

export async function getOfficialBySlug(slug: string, cityFips = RICHMOND_FIPS) {
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
}

export async function getOfficialVotingRecord(officialId: string) {
  const { data, error } = await supabase
    .from('votes')
    .select(`
      id,
      vote_choice,
      official_name,
      motions!inner (
        id,
        motion_text,
        result,
        vote_tally,
        agenda_items!inner (
          id,
          item_number,
          title,
          category,
          topic_label,
          public_comment_count,
          is_consent_calendar,
          meetings!inner (
            id,
            meeting_date,
            meeting_type
          )
        )
      )
    `)
    .eq('official_id', officialId)
    .order('id', { ascending: false })

  if (error) {
    console.error('getOfficialVotingRecord query failed:', error)
    return []
  }
  return data ?? []
}

export async function getOfficialContributions(
  officialId: string,
  cityFips = RICHMOND_FIPS
): Promise<DonorContribution[]> {
  // Find committees linked to this official
  const { data: committees } = await supabase
    .from('committees')
    .select('id')
    .eq('official_id', officialId)
    .eq('city_fips', cityFips)

  const committeeIds = (committees ?? []).map((c) => c.id)
  if (committeeIds.length === 0) return []

  // Get all contributions with dates for client-side aggregation
  const { data, error } = await supabase
    .from('contributions')
    .select('amount, contribution_date, source, donors!inner(name, employer, donor_pattern)')
    .in('committee_id', committeeIds)
    .eq('city_fips', cityFips)

  if (error) {
    console.error('getOfficialContributions query failed:', error)
    return []
  }

  const results: DonorContribution[] = []
  for (const row of data ?? []) {
    const donor = (row as Record<string, unknown>).donors as {
      name: string
      employer: string | null
      donor_pattern: string | null
    }

    // Skip government entities that appear as "donors" in filing data
    // (public financing, refunds, inter-committee transfers, etc.)
    const nameLower = donor.name.toLowerCase()
    if (/^(the )?(city|county|state|town) of\b/.test(nameLower)) continue

    results.push({
      donor_name: donor.name,
      donor_employer: donor.employer,
      donor_pattern: donor.donor_pattern,
      amount: row.amount as number,
      contribution_date: row.contribution_date as string,
      source: row.source as string,
    })
  }

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
      location, source_url,
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
      statement_type: filing?.statement_type ?? null,
      period_start: filing?.period_start ?? null,
      period_end: filing?.period_end ?? null,
      filer_name: filing?.filer_name ?? null,
      filing_source: filing?.source ?? null,
      filing_source_url: filing?.source_url ?? null,
    }
  })
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

  // Count votes cast by this official
  const { count: voteCount } = await supabase
    .from('votes')
    .select('id', { count: 'exact', head: true })
    .eq('official_id', officialId)

  // Attendance stats
  const { data: attendance } = await supabase
    .from('meeting_attendance')
    .select('status')
    .eq('official_id', officialId)

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
  const [meetings, items, votes, contributions, flags] = await Promise.all([
    supabase.from('meetings').select('id', { count: 'exact', head: true }).eq('city_fips', cityFips),
    supabase.from('agenda_items').select('id', { count: 'exact', head: true }),
    supabase.from('votes').select('id', { count: 'exact', head: true }),
    supabase.from('contributions').select('id', { count: 'exact', head: true }).eq('city_fips', cityFips),
    supabase.from('conflict_flags').select('id', { count: 'exact', head: true }).eq('city_fips', cityFips),
  ])

  const stats = {
    meetings: meetings.count ?? 0,
    agendaItems: items.count ?? 0,
    votes: votes.count ?? 0,
    contributions: contributions.count ?? 0,
    conflictFlags: flags.count ?? 0,
  }

  if (stats.meetings === 0) {
    console.warn('[Richmond Common] WARNING: getMeetingStats returned 0 meetings — possible Supabase connectivity issue during build/ISR')
  }

  return stats
}

// ─── Conflict Flags ──────────────────────────────────────────

export async function getConflictFlags(meetingId?: string, cityFips = RICHMOND_FIPS) {
  let query = supabase
    .from('conflict_flags')
    .select('*')
    .eq('city_fips', cityFips)
    .eq('is_current', true)
    .order('confidence', { ascending: false })

  if (meetingId) {
    query = query.eq('meeting_id', meetingId)
  }

  const { data, error } = await query
  if (error) {
    console.error('getConflictFlags query failed:', error)
    return [] as ConflictFlag[]
  }
  return filterGovernmentEntityFlags(data as ConflictFlag[])
}

// ─── Attendance ──────────────────────────────────────────────

export async function getAttendance(meetingId: string) {
  const { data, error } = await supabase
    .from('meeting_attendance')
    .select('*, officials(name, role)')
    .eq('meeting_id', meetingId)

  if (error) {
    console.error('getAttendance query failed:', error)
    return []
  }
  return data ?? []
}

// ─── Reports ────────────────────────────────────────────────

export async function getMeetingsWithFlags(cityFips = RICHMOND_FIPS) {
  // Server-side aggregation via RPC — avoids fetching 17K+ rows of JSONB evidence
  // which exceeded the anon role's 3s statement timeout
  const { data: flagCounts, error: rpcError } = await supabase
    .rpc('get_meeting_flag_counts', { p_city_fips: cityFips })

  if (rpcError) {
    console.error('getMeetingsWithFlags RPC failed:', rpcError)
    return []
  }

  const flagCountRows = (flagCounts ?? []) as Array<{
    meeting_id: string; flags_total: number; flags_published: number; items_scanned: number
  }>

  if (flagCountRows.length === 0) return []

  // Fetch the meeting details for all meetings that have flags
  // Batch the .in() call to avoid URL length limits (585 UUIDs × 36 chars)
  const meetingIds = flagCountRows.map(r => r.meeting_id)
  const BATCH_SIZE = 100
  const allMeetings: Meeting[] = []
  for (let i = 0; i < meetingIds.length; i += BATCH_SIZE) {
    const batch = meetingIds.slice(i, i + BATCH_SIZE)
    const { data: batchMeetings, error: meetingsError } = await supabase
      .from('meetings')
      .select('*')
      .in('id', batch)
      .order('meeting_date', { ascending: false })
    if (meetingsError) {
      console.error('getMeetingsWithFlags meetings batch failed:', meetingsError)
    }
    if (batchMeetings) allMeetings.push(...(batchMeetings as Meeting[]))
  }
  // Sort all results by date descending
  allMeetings.sort((a, b) => b.meeting_date.localeCompare(a.meeting_date))
  const meetings = allMeetings

  // Build lookup from RPC results
  const flagMap = new Map(flagCountRows.map(r => [r.meeting_id, r]))

  return (meetings ?? []).map((m) => ({
    ...(m as Meeting),
    items_scanned: flagMap.get(m.id)?.items_scanned ?? 0,
    flags_total: flagMap.get(m.id)?.flags_total ?? 0,
    flags_published: flagMap.get(m.id)?.flags_published ?? 0,
  }))
}

/** Lightweight flag counts for the meetings index — returns Map<meeting_id, published_count> */
export async function getMeetingFlagCounts(cityFips = RICHMOND_FIPS): Promise<Map<string, number>> {
  // Server-side aggregation via RPC — same fix as getMeetingsWithFlags
  const { data: flagCounts, error } = await supabase
    .rpc('get_meeting_flag_counts', { p_city_fips: cityFips })

  if (error) {
    console.error('getMeetingFlagCounts RPC failed:', error)
    return new Map()
  }

  const map = new Map<string, number>()
  for (const row of (flagCounts ?? []) as Array<{ meeting_id: string; flags_published: number }>) {
    if (row.flags_published > 0) {
      map.set(row.meeting_id, row.flags_published)
    }
  }
  return map
}

export async function getConflictFlagsDetailed(meetingId: string, cityFips = RICHMOND_FIPS) {
  const { data, error } = await supabase
    .from('conflict_flags')
    .select('*, agenda_items(title, item_number, category), officials(name)')
    .eq('meeting_id', meetingId)
    .eq('city_fips', cityFips)
    .eq('is_current', true)
    .order('confidence', { ascending: false })

  if (error) {
    console.error('getConflictFlagsDetailed query failed:', error)
    return []
  }
  const filtered = filterGovernmentEntityFlags(data as Array<{ flag_type: string; evidence: Record<string, unknown>[] } & Record<string, unknown>>)
  return filtered.map((f) => ({
    ...(f as unknown as ConflictFlag),
    agenda_item_title: (f.agenda_items as { title: string; item_number: string; category: string | null } | null)?.title ?? null,
    agenda_item_number: (f.agenda_items as { title: string; item_number: string; category: string | null } | null)?.item_number ?? null,
    agenda_item_category: (f.agenda_items as { title: string; item_number: string; category: string | null } | null)?.category ?? null,
    official_name: (f.officials as { name: string } | null)?.name ?? null,
  }))
}

// Lightweight meeting fetch for report detail — avoids full motions/votes/attendance load
export async function getMeetingForReport(meetingId: string): Promise<{ id: string; meeting_date: string; agenda_item_count: number } | null> {
  const { data: meeting, error } = await supabase
    .from('meetings')
    .select('id, meeting_date')
    .eq('id', meetingId)
    .single()

  if (error || !meeting) return null

  const { count } = await supabase
    .from('agenda_items')
    .select('id', { count: 'exact', head: true })
    .eq('meeting_id', meetingId)

  return {
    id: meeting.id as string,
    meeting_date: meeting.meeting_date as string,
    agenda_item_count: count ?? 0,
  }
}

// ─── Adjacent Meeting Navigation ─────────────────────────────

export interface AdjacentMeeting {
  id: string
  meeting_date: string
  meeting_type: string
}

export async function getAdjacentMeetings(
  meetingDate: string,
  bodyId: string | null,
  meetingType: string,
  cityFips = RICHMOND_FIPS
): Promise<{ previous: AdjacentMeeting | null; next: AdjacentMeeting | null }> {
  // Scope navigation to same body (or same meeting_type as fallback)
  const buildQuery = (direction: 'previous' | 'next') => {
    let query = supabase
      .from('meetings')
      .select('id, meeting_date, meeting_type')
      .eq('city_fips', cityFips)

    if (bodyId) {
      query = query.eq('body_id', bodyId)
    } else {
      query = query.eq('meeting_type', meetingType)
    }

    if (direction === 'previous') {
      query = query.lt('meeting_date', meetingDate).order('meeting_date', { ascending: false })
    } else {
      query = query.gt('meeting_date', meetingDate).order('meeting_date', { ascending: true })
    }

    return query.limit(1).single()
  }

  const [prevResult, nextResult] = await Promise.all([
    buildQuery('previous'),
    buildQuery('next'),
  ])

  return {
    previous: prevResult.data ? {
      id: prevResult.data.id as string,
      meeting_date: prevResult.data.meeting_date as string,
      meeting_type: prevResult.data.meeting_type as string,
    } : null,
    next: nextResult.data ? {
      id: nextResult.data.id as string,
      meeting_date: nextResult.data.meeting_date as string,
      meeting_type: nextResult.data.meeting_type as string,
    } : null,
  }
}

// ─── Financial Connections (S10.4) ───────────────────────────

export async function getFinancialConnectionsForOfficial(
  officialId: string,
  cityFips = RICHMOND_FIPS
): Promise<FinancialConnectionFlag[]> {
  // Query 1: Get all published conflict flags for this official
  const { data: rawFlags, error: flagError } = await supabase
    .from('conflict_flags')
    .select(`
      id, flag_type, confidence, description, evidence,
      meeting_id, agenda_item_id,
      meetings!inner(meeting_date),
      agenda_items!inner(title, item_number, category)
    `)
    .eq('official_id', officialId)
    .eq('city_fips', cityFips)
    .eq('is_current', true)
    .gte('confidence', CONFIDENCE_PUBLISHED)
    .order('confidence', { ascending: false })
    .limit(500)

  if (flagError) throw flagError
  if (!rawFlags || rawFlags.length === 0) return []

  // Query 2: Get votes for this official on the flagged agenda items
  // Join path: agenda_item_id → motions → votes
  const agendaItemIds = [...new Set(rawFlags.map((f) => f.agenda_item_id).filter(Boolean))]

  // Batch the .in() query to avoid Supabase URL length limits
  const BATCH_SIZE = 200
  type MotionVoteRow = { agenda_item_id: string; sequence_number: number; result: string; vote_tally: string | null; votes: Array<{ vote_choice: string }> }
  const allMotionVotes: MotionVoteRow[] = []
  for (let i = 0; i < agendaItemIds.length; i += BATCH_SIZE) {
    const batch = agendaItemIds.slice(i, i + BATCH_SIZE)
    const { data: motionVotesBatch, error: voteError } = await supabase
      .from('motions')
      .select('agenda_item_id, sequence_number, result, vote_tally, votes!inner(vote_choice)')
      .in('agenda_item_id', batch)
      .eq('votes.official_id', officialId)
      .order('sequence_number', { ascending: false })
    if (voteError) throw voteError
    if (motionVotesBatch) allMotionVotes.push(...(motionVotesBatch as unknown as MotionVoteRow[]))
  }
  const motionVotes = allMotionVotes

  // Build vote lookup: for each agenda item, take the highest sequence_number motion's vote
  const voteByAgendaItem = new Map<string, { vote_choice: string; motion_result: string; is_unanimous: boolean | null }>()
  for (const m of motionVotes ?? []) {
    const itemId = m.agenda_item_id
    if (!voteByAgendaItem.has(itemId)) {
      const votes = m.votes as unknown as Array<{ vote_choice: string }>
      if (votes.length > 0) {
        const tally = parseVoteTally(m.vote_tally)
        voteByAgendaItem.set(itemId, {
          vote_choice: votes[0].vote_choice,
          motion_result: m.result,
          is_unanimous: tally ? (tally.nays === 0 || tally.ayes === 0) : null,
        })
      }
    }
  }

  // Merge flags with vote data
  return rawFlags.map((f) => {
    const meeting = f.meetings as unknown as { meeting_date: string }
    const item = f.agenda_items as unknown as { title: string; item_number: string; category: string | null }
    const vote = voteByAgendaItem.get(f.agenda_item_id)

    return {
      id: f.id,
      flag_type: f.flag_type,
      confidence: f.confidence,
      description: f.description,
      evidence: f.evidence as Record<string, unknown>[],
      meeting_id: f.meeting_id,
      meeting_date: meeting.meeting_date,
      agenda_item_id: f.agenda_item_id,
      agenda_item_title: item.title,
      agenda_item_number: item.item_number,
      agenda_item_category: item.category,
      vote_choice: (vote?.vote_choice as FinancialConnectionFlag['vote_choice']) ?? null,
      motion_result: vote?.motion_result ?? null,
      is_unanimous: vote?.is_unanimous ?? null,
    }
  })
}

export function buildOfficialConnectionSummary(
  officialId: string,
  officialName: string,
  flags: FinancialConnectionFlag[]
): OfficialConnectionSummary {
  const flagTypeBreakdown: Record<string, number> = {}
  let votedInFavor = 0
  let votedAgainst = 0
  let abstained = 0
  let absentFor = 0
  let noVoteRecorded = 0

  for (const flag of flags) {
    flagTypeBreakdown[flag.flag_type] = (flagTypeBreakdown[flag.flag_type] ?? 0) + 1

    // Only count voted_in_favor / voted_against for non-unanimous (contested) votes.
    // Unanimous votes are noise — every member voted the same way.
    const isContested = flag.is_unanimous === false
    switch (flag.vote_choice) {
      case 'aye': if (isContested) votedInFavor++; break
      case 'nay': if (isContested) votedAgainst++; break
      case 'abstain': abstained++; break
      case 'absent': absentFor++; break
      default: noVoteRecorded++; break
    }
  }

  return {
    official_id: officialId,
    official_name: officialName,
    official_slug: nameToSlug(officialName),
    total_flags: flags.length,
    voted_in_favor: votedInFavor,
    voted_against: votedAgainst,
    abstained,
    absent_for: absentFor,
    no_vote_recorded: noVoteRecorded,
    flag_type_breakdown: flagTypeBreakdown,
    flags,
  }
}

export async function getAllFinancialConnectionSummaries(
  cityFips = RICHMOND_FIPS
): Promise<OfficialConnectionSummary[]> {
  // Fetch all published flags across all officials
  const { data: rawFlags, error: flagError } = await supabase
    .from('conflict_flags')
    .select(`
      id, flag_type, confidence, description, evidence,
      meeting_id, agenda_item_id, official_id,
      meetings!inner(meeting_date),
      agenda_items!inner(title, item_number, category),
      officials!inner(name)
    `)
    .eq('city_fips', cityFips)
    .eq('is_current', true)
    .gte('confidence', CONFIDENCE_PUBLISHED)
    .order('confidence', { ascending: false })
    .limit(1000)

  if (flagError) {
    console.error('getAllFinancialConnectionSummaries query failed:', flagError)
    return []
  }
  if (!rawFlags || rawFlags.length === 0) return []

  // Batch-fetch votes for all flagged agenda items across all officials
  const agendaItemIds = [...new Set(rawFlags.map((f) => f.agenda_item_id).filter(Boolean))]
  const officialIds = [...new Set(rawFlags.map((f) => f.official_id).filter(Boolean))]

  // Batch the .in() query to avoid Supabase URL length limits
  type AllMotionVoteRow = { agenda_item_id: string; sequence_number: number; result: string; vote_tally: string | null; votes: Array<{ official_id: string; vote_choice: string }> }
  const allMotionVotes: AllMotionVoteRow[] = []
  for (let i = 0; i < agendaItemIds.length; i += 200) {
    const batch = agendaItemIds.slice(i, i + 200)
    const { data: motionVotesBatch, error: voteError } = await supabase
      .from('motions')
      .select('agenda_item_id, sequence_number, result, vote_tally, votes!inner(official_id, vote_choice)')
      .in('agenda_item_id', batch)
      .in('votes.official_id', officialIds)
      .order('sequence_number', { ascending: false })
    if (voteError) {
      console.error('getAllFinancialConnectionSummaries vote query failed:', voteError)
      break
    }
    if (motionVotesBatch) allMotionVotes.push(...(motionVotesBatch as unknown as AllMotionVoteRow[]))
  }
  const motionVotes = allMotionVotes

  // Build vote lookup: (agenda_item_id, official_id) → vote
  // Also track unanimity per agenda item (shared across officials)
  const voteKey = (itemId: string, officialId: string) => `${itemId}::${officialId}`
  const voteMap = new Map<string, { vote_choice: string; motion_result: string; is_unanimous: boolean | null }>()
  const unanimityByItem = new Map<string, boolean | null>()
  for (const m of motionVotes ?? []) {
    // Compute unanimity once per agenda item (from the highest-sequence motion)
    if (!unanimityByItem.has(m.agenda_item_id)) {
      const tally = parseVoteTally(m.vote_tally)
      unanimityByItem.set(m.agenda_item_id, tally ? (tally.nays === 0 || tally.ayes === 0) : null)
    }
    const is_unanimous = unanimityByItem.get(m.agenda_item_id) ?? null
    const votes = m.votes as unknown as Array<{ official_id: string; vote_choice: string }>
    for (const v of votes) {
      const key = voteKey(m.agenda_item_id, v.official_id)
      if (!voteMap.has(key)) {
        voteMap.set(key, { vote_choice: v.vote_choice, motion_result: m.result, is_unanimous })
      }
    }
  }

  // Group flags by official
  const officialFlagsMap = new Map<string, { name: string; flags: FinancialConnectionFlag[] }>()
  for (const f of rawFlags) {
    if (!f.official_id) continue
    const meeting = f.meetings as unknown as { meeting_date: string }
    const item = f.agenda_items as unknown as { title: string; item_number: string; category: string | null }
    const official = f.officials as unknown as { name: string }
    const vote = voteMap.get(voteKey(f.agenda_item_id, f.official_id))

    if (!officialFlagsMap.has(f.official_id)) {
      officialFlagsMap.set(f.official_id, { name: official.name, flags: [] })
    }

    officialFlagsMap.get(f.official_id)!.flags.push({
      id: f.id,
      flag_type: f.flag_type,
      confidence: f.confidence,
      description: f.description,
      evidence: f.evidence as Record<string, unknown>[],
      meeting_id: f.meeting_id,
      meeting_date: meeting.meeting_date,
      agenda_item_id: f.agenda_item_id,
      agenda_item_title: item.title,
      agenda_item_number: item.item_number,
      agenda_item_category: item.category,
      vote_choice: (vote?.vote_choice as FinancialConnectionFlag['vote_choice']) ?? null,
      motion_result: vote?.motion_result ?? null,
      is_unanimous: vote?.is_unanimous ?? null,
    })
  }

  // Build summaries sorted by flag count descending
  return Array.from(officialFlagsMap.entries())
    .map(([id, { name, flags }]) => buildOfficialConnectionSummary(id, name, flags))
    .sort((a, b) => b.total_flags - a.total_flags)
}

// ─── Helpers ─────────────────────────────────────────────────

export function officialToSlug(name: string): string {
  return name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '')
}

// ─── Public Records (NextRequest/CPRA) ──────────────────────

export async function getPublicRecordsStats(
  cityFips = RICHMOND_FIPS
): Promise<PublicRecordsStats> {
  const { data, error } = await supabase
    .from('nextrequest_requests')
    .select('status, days_to_close, submitted_date')
    .eq('city_fips', cityFips)

  if (error) {
    console.error('getPublicRecordsStats query failed:', error)
    return { totalRequests: 0, avgResponseDays: 0, onTimeRate: 0, currentlyOverdue: 0 }
  }
  const requests = data ?? []

  const total = requests.length
  const completed = requests.filter((r) => r.days_to_close !== null)
  const avgDays = completed.length > 0
    ? Math.round(completed.reduce((sum, r) => sum + (r.days_to_close ?? 0), 0) / completed.length)
    : 0
  const onTime = completed.filter((r) => (r.days_to_close ?? 999) <= 10).length
  const onTimeRate = completed.length > 0
    ? Math.round((onTime / completed.length) * 100)
    : 0

  // Currently overdue: not closed AND more than 10 days since submitted
  // Status values from NextRequest API: "Closed", "Open", "Due soon" (case varies)
  const closedStatuses = new Set(['closed', 'completed'])
  const now = new Date()
  const overdue = requests.filter((r) => {
    if (closedStatuses.has((r.status || '').toLowerCase())) return false
    if (!r.submitted_date) return false
    const submitted = new Date(r.submitted_date + 'T00:00:00')
    const daysSince = Math.floor((now.getTime() - submitted.getTime()) / (1000 * 60 * 60 * 24))
    return daysSince > 10
  }).length

  return {
    totalRequests: total,
    avgResponseDays: avgDays,
    onTimeRate,
    currentlyOverdue: overdue,
  }
}

export async function getDepartmentCompliance(
  cityFips = RICHMOND_FIPS
): Promise<DepartmentCompliance[]> {
  const { data, error } = await supabase
    .from('nextrequest_requests')
    .select('department, days_to_close, status')
    .eq('city_fips', cityFips)

  if (error) {
    console.error('getDepartmentCompliance query failed:', error)
    return []
  }

  // Group by department
  const deptMap = new Map<string, { requests: typeof data }>()
  for (const r of data ?? []) {
    const dept = r.department || 'Unknown'
    const existing = deptMap.get(dept) ?? { requests: [] }
    existing.requests.push(r)
    deptMap.set(dept, existing)
  }

  return Array.from(deptMap.entries()).map(([dept, { requests }]) => {
    const completed = requests.filter((r) => r.days_to_close !== null)
    const avgDays = completed.length > 0
      ? Math.round(completed.reduce((sum, r) => sum + (r.days_to_close ?? 0), 0) / completed.length)
      : 0
    const onTime = completed.filter((r) => (r.days_to_close ?? 999) <= 10).length
    const onTimeRate = completed.length > 0 ? Math.round((onTime / completed.length) * 100) : 0
    const slowest = Math.max(...completed.map((r) => r.days_to_close ?? 0), 0)

    return {
      department: dept,
      requestCount: requests.length,
      avgDays,
      onTimeRate,
      slowestDays: slowest,
    }
  }).sort((a, b) => b.requestCount - a.requestCount)
}

export async function getRecentRequests(
  limit = 20,
  cityFips = RICHMOND_FIPS
): Promise<NextRequestRequest[]> {
  const { data, error } = await supabase
    .from('nextrequest_requests')
    .select('*')
    .eq('city_fips', cityFips)
    .order('submitted_date', { ascending: false })
    .limit(limit)

  if (error) {
    console.error('getRecentRequests query failed:', error)
    return [] as NextRequestRequest[]
  }
  return (data ?? []) as NextRequestRequest[]
}

export async function getAllPublicRecords(
  cityFips = RICHMOND_FIPS
): Promise<NextRequestRequest[]> {
  const { data, error } = await supabase
    .from('nextrequest_requests')
    .select('*')
    .eq('city_fips', cityFips)
    .order('submitted_date', { ascending: false })
    .range(0, 2499)

  if (error) {
    console.error('getAllPublicRecords query failed:', error)
    return [] as NextRequestRequest[]
  }
  return (data ?? []) as NextRequestRequest[]
}

// ─── Commissions ─────────────────────────────────────────

export async function getCommissions(
  cityFips = RICHMOND_FIPS
): Promise<CommissionWithStats[]> {
  const { data: commissions, error } = await supabase
    .from('commissions')
    .select('*')
    .eq('city_fips', cityFips)
    .order('name')

  if (error) {
    console.error('getCommissions query failed:', error)
    return [] as CommissionWithStats[]
  }
  warnIfEmpty('getCommissions', commissions)

  const commissionIds = (commissions ?? []).map((c) => c.id)
  if (commissionIds.length === 0) return []

  // Count current members per commission, separating active-term from holdovers
  const { data: members } = await supabase
    .from('commission_members')
    .select('commission_id, term_end')
    .in('commission_id', commissionIds)
    .eq('is_current', true)

  const today = new Date().toISOString().split('T')[0]
  const activeCountMap = new Map<string, number>()
  const holdoverCountMap = new Map<string, number>()
  for (const m of members ?? []) {
    const isExpired = m.term_end && m.term_end < today
    if (isExpired) {
      holdoverCountMap.set(m.commission_id, (holdoverCountMap.get(m.commission_id) ?? 0) + 1)
    } else {
      activeCountMap.set(m.commission_id, (activeCountMap.get(m.commission_id) ?? 0) + 1)
    }
  }

  return (commissions ?? []).map((c) => {
    const commission = c as Commission
    const activeCount = activeCountMap.get(commission.id) ?? 0
    const holdoverCount = holdoverCountMap.get(commission.id) ?? 0
    const vacancyCount = commission.num_seats
      ? Math.max(0, commission.num_seats - activeCount)
      : 0
    return {
      ...commission,
      member_count: activeCount,
      holdover_count: holdoverCount,
      vacancy_count: vacancyCount,
    }
  })
}

export async function getCommission(
  commissionId: string,
  cityFips = RICHMOND_FIPS
): Promise<{ commission: Commission; members: CommissionMember[] } | null> {
  const { data: commission, error } = await supabase
    .from('commissions')
    .select('*')
    .eq('id', commissionId)
    .eq('city_fips', cityFips)
    .single()

  if (error || !commission) return null

  const { data: members } = await supabase
    .from('commission_members')
    .select('*')
    .eq('commission_id', commissionId)
    .eq('is_current', true)
    .order('name')

  return {
    commission: commission as Commission,
    members: (members ?? []) as CommissionMember[],
  }
}

export async function getCommissionStaleness(
  cityFips = RICHMOND_FIPS
): Promise<CommissionStaleness[]> {
  const { data, error } = await supabase
    .from('v_commission_staleness')
    .select('*')
    .eq('city_fips', cityFips)

  if (error) {
    console.error('getCommissionStaleness query failed:', error)
    return [] as CommissionStaleness[]
  }
  return (data ?? []) as CommissionStaleness[]
}

export async function getCommissionMeetings(
  commissionId: string,
  cityFips = RICHMOND_FIPS
): Promise<MeetingWithCounts[]> {
  // Step 1: Find the body linked to this commission
  const { data: body } = await supabase
    .from('bodies')
    .select('id')
    .eq('commission_id', commissionId)
    .eq('city_fips', cityFips)
    .single()

  if (!body) return []

  // Step 2: Fetch meetings for this body + counts via RPC
  const [{ data: meetings, error }, { data: counts }] = await Promise.all([
    supabase
      .from('meetings')
      .select('*')
      .eq('body_id', body.id)
      .eq('city_fips', cityFips)
      .order('meeting_date', { ascending: false }),
    supabase.rpc('get_meeting_counts', { p_city_fips: cityFips }),
  ])

  if (error || !meetings) return []

  interface MeetingCounts {
    meeting_id: string
    agenda_item_count: number
    vote_count: number
    categories: CategoryCount[]
    topic_labels: TopicLabelCount[]
  }

  const countMap = new Map(
    ((counts ?? []) as MeetingCounts[]).map((c) => [c.meeting_id, c])
  )

  return (meetings as Meeting[]).map((m) => {
    const c = countMap.get(m.id)
    const allCats = c?.categories ?? []
    const allLabels = c?.topic_labels ?? []
    return {
      ...m,
      agenda_item_count: Number(c?.agenda_item_count ?? 0),
      vote_count: Number(c?.vote_count ?? 0),
      top_categories: allCats.slice(0, 4),
      all_categories: allCats,
      top_topic_labels: allLabels.slice(0, 5),
      all_topic_labels: allLabels,
    }
  })
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

async function fetchVotesForAlignment(cityFips = RICHMOND_FIPS): Promise<ContestedVoteRow[]> {
  const { data: votes, error } = await supabase
    .rpc('get_contested_votes', { p_city_fips: cityFips })

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
  blocs: VotingBloc[]
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

  const currentIds = new Set((currentOfficials ?? []).map((o) => o.id))

  const allVotes = await fetchVotesForAlignment(cityFips)

  // Filter to votes by current council members only
  const votes = allVotes.filter((v) => currentIds.has(v.official_id))

  // The RPC already filtered to contested motions server-side, but after filtering
  // to current members only, some motions may no longer be contested (e.g., a motion
  // where the only dissenter was a former member). Re-check contestedness.
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

  // Re-check: only keep motions that are still contested among current members
  for (const [motionId, motionVotes] of votesByMotion) {
    const choices = new Set(motionVotes.map((v) => v.vote_choice))
    if (choices.size < 2) {
      votesByMotion.delete(motionId)
    }
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

  // Detect voting blocs: groups of 3+ members mutually aligned above threshold
  const overallAlignments = alignments.filter((a) => a.category === null)
  const blocs = detectBlocs(overallAlignments, officials)

  // Compute category divergences: pairs where category alignment differs significantly from overall
  const divergences = computeDivergences(alignments)

  return { alignments, blocs, divergences, officials }
}

const STRONG_BLOC_THRESHOLD = 0.85
const MODERATE_BLOC_THRESHOLD = 0.70
const MIN_SHARED_VOTES = 5

/**
 * Detect voting blocs: groups of 3+ members who are all mutually aligned above threshold.
 * Brute-force clique finding — filters to officials with enough vote data and caps
 * subset size at MAX_BLOC_SIZE to avoid combinatorial explosion.
 * (30 historical officials × uncapped subsets ≈ 2^30 = 1 billion checks.
 *  With filtering + cap: ~3K checks.)
 */
const MAX_BLOC_SIZE = 7  // Richmond council has 7 members; blocs can't be larger

function detectBlocs(
  overallAlignments: PairwiseAlignment[],
  officials: Array<{ id: string; name: string }>,
): VotingBloc[] {
  // Build lookup: pairKey -> agreement_rate
  const pairRates = new Map<string, { rate: number; votes: number }>()
  for (const a of overallAlignments) {
    const [first, second] = a.official_a_id < a.official_b_id
      ? [a.official_a_id, a.official_b_id]
      : [a.official_b_id, a.official_a_id]
    pairRates.set(`${first}|${second}`, { rate: a.agreement_rate, votes: a.total_shared_votes })
  }

  const getMutualRate = (idA: string, idB: string) => {
    const [first, second] = idA < idB ? [idA, idB] : [idB, idA]
    return pairRates.get(`${first}|${second}`)
  }

  // Only include officials who have at least one valid alignment pair
  // (enough shared contested votes). Filters out former members with
  // sparse histories, reducing candidates from ~30 to ~10-12.
  const activeOfficials = new Set<string>()
  for (const a of overallAlignments) {
    if (a.total_shared_votes >= MIN_SHARED_VOTES) {
      activeOfficials.add(a.official_a_id)
      activeOfficials.add(a.official_b_id)
    }
  }

  const blocs: VotingBloc[] = []
  const ids = officials
    .filter((o) => activeOfficials.has(o.id))
    .map((o) => o.id)

  // Check subsets from MAX_BLOC_SIZE down to 3
  const maxSize = Math.min(ids.length, MAX_BLOC_SIZE)
  for (let size = maxSize; size >= 3; size--) {
    const subsets = getSubsets(ids, size)
    for (const subset of subsets) {
      // Check if all pairs in this subset meet threshold
      let minRate = 1
      let allSufficient = true
      const rates: number[] = []

      for (let i = 0; i < subset.length && allSufficient; i++) {
        for (let j = i + 1; j < subset.length && allSufficient; j++) {
          const pair = getMutualRate(subset[i], subset[j])
          if (!pair || pair.votes < MIN_SHARED_VOTES) {
            allSufficient = false
            break
          }
          rates.push(pair.rate)
          if (pair.rate < minRate) minRate = pair.rate
        }
      }

      if (!allSufficient || minRate < MODERATE_BLOC_THRESHOLD) continue

      // Check this bloc isn't a subset of an already-found bloc
      const isSubsetOfExisting = blocs.some((existingBloc) => {
        const existingIds = new Set(existingBloc.members.map((m) => m.id))
        return subset.every((id) => existingIds.has(id))
      })

      if (isSubsetOfExisting) continue

      const avgRate = rates.reduce((a, b) => a + b, 0) / rates.length
      blocs.push({
        members: subset.map((id) => ({
          id,
          name: officials.find((o) => o.id === id)?.name ?? id,
        })),
        category: null,
        avg_mutual_agreement: Math.round(avgRate * 1000) / 1000,
        bloc_strength: minRate >= STRONG_BLOC_THRESHOLD ? 'strong' : 'moderate',
      })
    }
  }

  return blocs
}

/** Generate all subsets of a given size from an array. */
function getSubsets(arr: string[], size: number): string[][] {
  if (size === 0) return [[]]
  if (arr.length < size) return []
  const result: string[][] = []
  for (let i = 0; i <= arr.length - size; i++) {
    const rest = getSubsets(arr.slice(i + 1), size - 1)
    for (const r of rest) {
      result.push([arr[i], ...r])
    }
  }
  return result
}

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

// ─── Site Search (S10.1) ────────────────────────────────────

export async function searchSite(
  query: string,
  options?: {
    resultType?: SearchResultType
    limit?: number
    offset?: number
    cityFips?: string
  }
): Promise<SearchResult[]> {
  const { data, error } = await supabase.rpc('search_site', {
    p_query: query,
    p_city_fips: options?.cityFips ?? RICHMOND_FIPS,
    p_result_type: options?.resultType ?? null,
    p_limit: options?.limit ?? 20,
    p_offset: options?.offset ?? 0,
  })

  if (error) {
    console.error('Search error:', error)
    return []
  }

  return (data ?? []) as SearchResult[]
}

// ─── Influence Map: Item Center (S14-C) ─────────────────────

/**
 * Fetch the full influence map data bundle for a single agenda item.
 * This is the main query for /influence/item/[id].
 *
 * Strategy: Start from conflict_flags for this item (the scanner's output),
 * then enrich with contribution details, vote context, and fundraising totals
 * via separate focused queries. Each query is simple and composable.
 */
export async function getItemInfluenceMapData(
  agendaItemId: string,
  cityFips = RICHMOND_FIPS
): Promise<ItemInfluenceMapData | null> {
  // 1. Get the agenda item + meeting context
  const { data: item, error: itemError } = await supabase
    .from('agenda_items')
    .select(`
      id, title, item_number, description, plain_language_summary,
      summary_headline, category, financial_amount, is_consent_calendar,
      was_pulled_from_consent, resolution_number, meeting_id,
      meetings!inner(meeting_date, minutes_url)
    `)
    .eq('id', agendaItemId)
    .eq('meetings.city_fips', cityFips)
    .single()

  if (itemError || !item) {
    console.error('getItemInfluenceMapData: item query failed', { agendaItemId, itemError })
    return null
  }

  const meeting = item.meetings as unknown as {
    meeting_date: string
    minutes_url: string | null
  }

  // 2. Get all current conflict flags for this item
  const { data: flags } = await supabase
    .from('conflict_flags')
    .select('id, flag_type, description, evidence, confidence, official_id, match_details')
    .eq('agenda_item_id', agendaItemId)
    .eq('city_fips', cityFips)
    .eq('is_current', true)
    .gte('confidence', CONFIDENCE_PUBLISHED)
    .order('confidence', { ascending: false })

  const publishedFlags = (flags ?? []).filter(f => {
    if (f.flag_type !== 'donor_vendor_expenditure') return true
    const evidence = f.evidence as Record<string, unknown>[] | null
    const vendor = evidence?.[0]?.vendor
    if (typeof vendor === 'string' && isGovernmentEntity(vendor)) return false
    return true
  })

  // 3. Get all votes on this item (via motions)
  const votes = await getItemVotes(agendaItemId, cityFips)

  // 4. Build contribution narratives from flags + enrichment
  const contributions = await buildContributionNarratives(
    agendaItemId, publishedFlags, votes, cityFips
  )

  // 5. Get behested payments for entities in this item
  const behested_payments = await getBehstedPaymentsForItem(
    agendaItemId, publishedFlags, cityFips
  )

  // 6. Get related agenda items (same officials or entities)
  const related_items = await getRelatedAgendaItems(
    agendaItemId, publishedFlags, cityFips
  )

  return {
    item: {
      id: item.id as string,
      title: item.title as string,
      item_number: item.item_number as string,
      description: item.description as string | null,
      plain_language_summary: item.plain_language_summary as string | null,
      summary_headline: item.summary_headline as string | null,
      category: item.category as string | null,
      financial_amount: item.financial_amount as string | null,
      is_consent_calendar: item.is_consent_calendar as boolean,
      was_pulled_from_consent: item.was_pulled_from_consent as boolean,
      resolution_number: item.resolution_number as string | null,
      meeting_id: item.meeting_id as string,
      meeting_date: meeting.meeting_date,
    },
    votes,
    contributions,
    behested_payments,
    related_items,
    total_flags: publishedFlags.length,
    source_url: meeting.minutes_url,
    extracted_at: null,
  }
}

/** Get all votes on an agenda item with official context */
async function getItemVotes(
  agendaItemId: string,
  cityFips: string,
): Promise<ItemVoteContext[]> {
  const { data: motions } = await supabase
    .from('motions')
    .select(`
      id, result,
      votes(vote_choice, officials!inner(id, name))
    `)
    .eq('agenda_item_id', agendaItemId)
    .order('sequence_number', { ascending: false })
    .limit(1) // Take the final/decisive motion

  if (!motions || motions.length === 0) return []

  const motion = motions[0]
  const votes = motion.votes as unknown as Array<{
    vote_choice: string
    officials: { id: string; name: string }
  }>

  return votes.map(v => ({
    official_id: v.officials.id,
    official_name: v.officials.name,
    official_slug: nameToSlug(v.officials.name),
    vote_choice: v.vote_choice,
    motion_result: motion.result as string,
  }))
}

/**
 * Build enriched contribution narratives from conflict flags.
 *
 * For each flag with an official_id, query the contributions table
 * to get the actual financial records, then compute contextual data
 * (% of fundraising, same-way voters).
 */
async function buildContributionNarratives(
  agendaItemId: string,
  flags: Array<{ id: string; flag_type: string; description: string; evidence: unknown; confidence: number; official_id: string | null; match_details?: Record<string, unknown> | null }>,
  votes: ItemVoteContext[],
  cityFips: string,
): Promise<ContributionNarrativeData[]> {
  // Filter to contribution-related flags that have an official
  const contributionFlags = flags.filter(f =>
    f.official_id &&
    (f.flag_type === 'campaign_contribution' ||
     f.flag_type === 'vendor_donor_match' ||
     f.flag_type === 'donor_vendor_expenditure' ||
     f.flag_type === 'llc_ownership_chain')
  )

  if (contributionFlags.length === 0) return []

  // Get unique official IDs
  const officialIds = [...new Set(contributionFlags.map(f => f.official_id!).filter(Boolean))]

  // Batch: get official details + their committees
  const { data: officials } = await supabase
    .from('officials')
    .select('id, name')
    .in('id', officialIds)

  if (!officials || officials.length === 0) return []

  // Get committees for these officials
  const { data: committees } = await supabase
    .from('committees')
    .select('id, name, official_id')
    .in('official_id', officialIds)
    .eq('city_fips', cityFips)

  if (!committees || committees.length === 0) return []

  // Get all contributions to these committees
  const committeeIds = committees.map(c => c.id as string)
  const { data: allContribs, error: contribError } = await supabase
    .from('contributions')
    .select(`
      id, amount, contribution_date, source, filing_id,
      donor_id, committee_id,
      donors!inner(name, employer)
    `)
    .in('committee_id', committeeIds)
    .eq('city_fips', cityFips)
    .order('contribution_date', { ascending: false })
    .limit(5000) // Reasonable upper bound

  if (contribError) console.error('buildContributionNarratives: contributions query failed', contribError.message)
  if (!allContribs || allContribs.length === 0) return []

  // Build lookup: committee_id -> official_id
  const committeeToOfficial = new Map<string, string>()
  for (const c of committees) {
    if (c.official_id) committeeToOfficial.set(c.id as string, c.official_id as string)
  }

  // Build official lookup
  const officialMap = new Map<string, { name: string; slug: string }>()
  for (const o of officials) {
    officialMap.set(o.id as string, { name: o.name as string, slug: nameToSlug(o.name as string) })
  }

  // Compute per-official total fundraising
  const officialTotals = new Map<string, number>()
  for (const c of allContribs) {
    const officialId = committeeToOfficial.get(c.committee_id as string)
    if (officialId) {
      officialTotals.set(officialId, (officialTotals.get(officialId) ?? 0) + Number(c.amount))
    }
  }

  // Build vote lookup
  const voteByOfficial = new Map<string, string>()
  for (const v of votes) {
    voteByOfficial.set(v.official_id, v.vote_choice)
  }

  // Now build narratives: extract donor names from flag descriptions
  // and match against contribution records
  const narratives: ContributionNarrativeData[] = []

  for (const flag of contributionFlags) {
    const officialId = flag.official_id!
    const officialInfo = officialMap.get(officialId)
    if (!officialInfo) continue

    // Find committees belonging to this official
    const officialCommitteeIds = committees
      .filter(c => c.official_id === officialId)
      .map(c => c.id as string)

    // Get contributions to this official's committees
    const officialContribs = allContribs.filter(
      c => officialCommitteeIds.includes(c.committee_id as string)
    )

    // Group contributions by donor for this official
    type DonorGroup = {
      donor_name: string
      donor_employer: string | null
      contributions: typeof allContribs
      total: number
    }
    const donorGroups = new Map<string, DonorGroup>()
    // Also group by employer for vendor-to-employer matching
    const employerGroups = new Map<string, DonorGroup>()

    for (const contrib of officialContribs) {
      const donor = contrib.donors as unknown as { name: string; employer: string | null }
      const key = donor.name.toLowerCase()
      const group = donorGroups.get(key) ?? {
        donor_name: donor.name,
        donor_employer: donor.employer,
        contributions: [],
        total: 0,
      }
      group.contributions.push(contrib)
      group.total += Number(contrib.amount)
      donorGroups.set(key, group)

      // Build employer index — aggregates all employees at each employer
      if (donor.employer) {
        const empKey = donor.employer.toLowerCase()
        const empGroup = employerGroups.get(empKey) ?? {
          donor_name: donor.employer, // Use employer as display name
          donor_employer: donor.employer,
          contributions: [],
          total: 0,
        }
        empGroup.contributions.push(contrib)
        empGroup.total += Number(contrib.amount)
        employerGroups.set(empKey, empGroup)
      }
    }

    // Extract donor/entity name from match_details based on flag type
    const md = flag.match_details as Record<string, unknown> | null
    let matchedEntityName: string | undefined
    let matchByEmployer = false
    let vendorExpTotal: number | undefined
    let vendorExpCount: number | undefined
    let entityName: string | undefined
    let entityRelationship: string | undefined

    if (flag.flag_type === 'donor_vendor_expenditure') {
      // Vendor name is the entity — match against donor name or employer
      matchedEntityName = (md?.vendor as string | undefined)?.toLowerCase()
      const matchType = md?.donor_match_type as string | undefined
      matchByEmployer = matchType?.includes('employer') ?? false
      vendorExpTotal = md?.total_expenditure as number | undefined
      vendorExpCount = md?.expenditure_count as number | undefined
      entityName = md?.vendor as string | undefined
      entityRelationship = matchByEmployer ? 'employer' : 'direct'

      // Filter out government entity vendors — "city of richmond" as an employer
      // is civic noise, not a conflict signal (mirrors scanner-side filter)
      if (entityName && isGovernmentEntity(entityName)) continue
    } else if (flag.flag_type === 'llc_ownership_chain') {
      matchedEntityName = (md?.donor_name as string | undefined)?.toLowerCase()
      entityName = md?.org_name as string | undefined
      entityRelationship = md?.role as string | undefined ?? 'organization'
    } else {
      matchedEntityName = (md?.donor_name as string | undefined)?.toLowerCase()
    }

    // Find matching donor group using multi-strategy matching
    // For employer-matched vendor flags, search employer groups first (aggregated)
    const descLower = flag.description.toLowerCase()
    const searchGroups: Array<[string, DonorGroup]> = matchByEmployer
      ? [...employerGroups.entries()]
      : [...donorGroups.entries()]

    for (const [, group] of searchGroups) {
      const groupNameLower = group.donor_name.toLowerCase()

      let matched = false

      if (matchedEntityName && matchedEntityName.length > 3) {
        // Strategy 1: exact match
        if (groupNameLower === matchedEntityName) {
          matched = true
        }
        // Strategy 2: substring match
        else if (groupNameLower.includes(matchedEntityName) || matchedEntityName.includes(groupNameLower)) {
          matched = true
        }
      } else if (!matchedEntityName) {
        // Strategy 3: legacy description parsing (for flags without match_details)
        if (groupNameLower.length <= 3) continue
        if (!descLower.includes(groupNameLower)) continue
        matched = true
      }

      if (!matched) continue

      const officialTotal = officialTotals.get(officialId) ?? 0
      const voteChoice = voteByOfficial.get(officialId) ?? null

      // Count same-way voters and those without contributions from this donor
      const sameWayVoters = voteChoice
        ? votes.filter(v => v.vote_choice.toLowerCase() === voteChoice.toLowerCase() && v.official_id !== officialId)
        : []
      const sameWayWithoutContrib = sameWayVoters.filter(v => {
        // Check if this donor/employer contributed to this voter's committees
        const voterCommitteeIds = committees
          .filter(c => c.official_id === v.official_id)
          .map(c => c.id as string)
        return !allContribs.some(c => {
          if (!voterCommitteeIds.includes(c.committee_id as string)) return false
          const d = c.donors as unknown as { name: string; employer: string | null }
          if (matchByEmployer) {
            return (d.employer ?? '').toLowerCase() === groupNameLower
          }
          return d.name.toLowerCase() === groupNameLower
        })
      })

      const dates = group.contributions
        .map(c => c.contribution_date as string)
        .filter(Boolean)
        .sort()

      const contribRecords: ContributionRecord[] = group.contributions.map(c => {
        const donor = c.donors as unknown as { name: string; employer: string | null }
        const committeeId = c.committee_id as string
        const committee = committees.find(cm => cm.id === committeeId)
        return {
          contribution_id: c.id as string,
          donor_name: donor.name,
          donor_employer: donor.employer,
          committee_name: (committee?.name as string) ?? 'Unknown Committee',
          official_name: officialInfo.name,
          official_id: officialId,
          official_slug: officialInfo.slug,
          amount: Number(c.amount),
          contribution_date: c.contribution_date as string,
          source: c.source as string,
          filing_id: c.filing_id as string | null,
        }
      })

      narratives.push({
        official_id: officialId,
        official_name: officialInfo.name,
        official_slug: officialInfo.slug,
        donor_name: group.donor_name,
        donor_employer: group.donor_employer,
        total_contributed: group.total,
        contribution_count: group.contributions.length,
        earliest_date: dates[0] ?? '',
        latest_date: dates[dates.length - 1] ?? '',
        official_total_fundraising: officialTotal,
        percentage_of_fundraising: officialTotal > 0
          ? Math.round((group.total / officialTotal) * 1000) / 10
          : 0,
        vote_choice: voteChoice,
        same_way_voter_count: sameWayVoters.length,
        same_way_without_contribution: sameWayWithoutContrib.length,
        confidence: flag.confidence,
        source_tier: 'Tier 1',
        source_date: dates[dates.length - 1] ?? '',
        contributions: contribRecords,
        source_url: null,
        flag_type: flag.flag_type,
        flag_description: flag.description,
        vendor_expenditure_total: vendorExpTotal,
        vendor_expenditure_count: vendorExpCount,
        entity_name: entityName,
        entity_relationship: entityRelationship,
      })
    }
  }

  // Deduplicate: same official + donor pair (can appear from multiple flags)
  const seen = new Set<string>()
  return narratives.filter(n => {
    const key = `${n.official_id}:${n.donor_name.toLowerCase()}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

/** Get behested payments for entities appearing in this item's conflict flags */
async function getBehstedPaymentsForItem(
  agendaItemId: string,
  flags: Array<{ id: string; flag_type: string; description: string; evidence: unknown; confidence: number; official_id: string | null }>,
  cityFips: string,
): Promise<BehstedPaymentNarrativeData[]> {
  // Get official IDs from flags
  const officialIds = [...new Set(flags.map(f => f.official_id).filter(Boolean) as string[])]
  if (officialIds.length === 0) return []

  // Query behested payments for these officials
  const { data: payments } = await supabase
    .from('behested_payments')
    .select('*')
    .in('official_id', officialIds)
    .eq('city_fips', cityFips)
    .order('payment_date', { ascending: false })
    .limit(50)

  if (!payments || payments.length === 0) return []

  // Check if payors are also campaign contributors
  const payorNames = [...new Set(payments.map(p => (p.payor_name as string).toLowerCase()))]

  // Simple: check if any donor names match payor names
  const { data: matchingDonors } = await supabase
    .from('donors')
    .select('name')
    .eq('city_fips', cityFips)
    .limit(1000)

  const donorNames = new Set(
    (matchingDonors ?? []).map(d => (d.name as string).toLowerCase())
  )

  return payments.map(p => ({
    id: p.id as string,
    official_name: p.official_name as string,
    official_id: p.official_id as string | null,
    payor_name: p.payor_name as string,
    payee_name: p.payee_name as string,
    payee_description: p.payee_description as string | null,
    amount: p.amount ? Number(p.amount) : null,
    payment_date: p.payment_date as string | null,
    filing_date: p.filing_date as string | null,
    source_url: p.source_url as string | null,
    is_also_contributor: payorNames.some(
      pn => pn === (p.payor_name as string).toLowerCase() && donorNames.has(pn)
    ),
    contributor_total: null, // TODO: compute actual total if is_also_contributor
  }))
}

/**
 * Find related agenda items — other items flagged with the same officials.
 * Returns two groups: same-official items (direct relationship) and
 * same-meeting items (temporal context). Sorted by controversy.
 */
async function getRelatedAgendaItems(
  agendaItemId: string,
  flags: Array<{ id: string; flag_type: string; description: string; evidence: unknown; confidence: number; official_id: string | null }>,
  cityFips: string,
): Promise<RelatedAgendaItem[]> {
  const officialIds = [...new Set(flags.map(f => f.official_id).filter(Boolean) as string[])]
  if (officialIds.length === 0) return []

  // Find other flagged items for these officials, last 4 years only
  const fourYearsAgo = new Date()
  fourYearsAgo.setFullYear(fourYearsAgo.getFullYear() - 4)
  const cutoffDate = fourYearsAgo.toISOString().split('T')[0]

  const { data: relatedFlags } = await supabase
    .from('conflict_flags')
    .select(`
      agenda_item_id,
      agenda_items!inner(
        id, title, summary_headline, meeting_id, category,
        meetings!inner(meeting_date)
      )
    `)
    .in('official_id', officialIds)
    .eq('city_fips', cityFips)
    .eq('is_current', true)
    .gte('confidence', CONFIDENCE_PUBLISHED)
    .gte('agenda_items.meetings.meeting_date', cutoffDate)
    .neq('agenda_item_id', agendaItemId)
    .order('confidence', { ascending: false })
    .limit(200)

  if (!relatedFlags || relatedFlags.length === 0) return []

  // Deduplicate by agenda item ID and count flags per item
  const itemMap = new Map<string, {
    item: RelatedAgendaItem
    count: number
  }>()

  for (const rf of relatedFlags) {
    const ai = rf.agenda_items as unknown as {
      id: string
      title: string
      summary_headline: string | null
      meeting_id: string
      category: string | null
      meetings: { meeting_date: string }
    }
    const itemId = ai.id
    const existing = itemMap.get(itemId)
    if (existing) {
      existing.count++
    } else {
      itemMap.set(itemId, {
        item: {
          id: itemId,
          title: ai.title,
          summary_headline: ai.summary_headline,
          meeting_id: ai.meeting_id,
          meeting_date: ai.meetings.meeting_date,
          category: ai.category,
          flag_count: 1,
          has_split_vote: false,
        },
        count: 1,
      })
    }
  }

  // Check for split votes on all related items
  const relatedItemIds = [...itemMap.keys()]
  if (relatedItemIds.length > 0) {
    const BATCH = 100
    for (let i = 0; i < relatedItemIds.length; i += BATCH) {
      const batch = relatedItemIds.slice(i, i + BATCH)
      const { data: motions } = await supabase
        .from('motions')
        .select('agenda_item_id, votes(vote_choice)')
        .in('agenda_item_id', batch)

      if (motions) {
        for (const m of motions) {
          const votes = m.votes as unknown as Array<{ vote_choice: string }>
          const hasNay = votes.some(v => v.vote_choice.toLowerCase() === 'nay')
          if (hasNay) {
            const entry = itemMap.get(m.agenda_item_id as string)
            if (entry) entry.item.has_split_vote = true
          }
        }
      }
    }
  }

  // Sort by controversy: split votes first, then flag count, then date
  return Array.from(itemMap.values())
    .map(({ item, count }) => ({ ...item, flag_count: count }))
    .sort((a, b) => {
      // Split votes always rank higher
      if (a.has_split_vote !== b.has_split_vote) return a.has_split_vote ? -1 : 1
      // Then by flag count descending
      if (a.flag_count !== b.flag_count) return b.flag_count - a.flag_count
      // Then by date descending
      return b.meeting_date.localeCompare(a.meeting_date)
    })
    .slice(0, 15)
}

/** Get a single agenda item's basic info (for metadata generation) */
export async function getAgendaItemBasic(
  agendaItemId: string,
  cityFips = RICHMOND_FIPS
) {
  const { data, error } = await supabase
    .from('agenda_items')
    .select('id, title, summary_headline, meeting_id, meetings!inner(meeting_date)')
    .eq('id', agendaItemId)
    .eq('meetings.city_fips', cityFips)
    .single()

  if (error || !data) return null
  const meeting = data.meetings as unknown as { meeting_date: string }
  return {
    id: data.id as string,
    title: data.title as string,
    summary_headline: data.summary_headline as string | null,
    meeting_id: data.meeting_id as string,
    meeting_date: meeting.meeting_date,
  }
}

// ─── Agenda Item Detail Page ────────────────────────────────

/**
 * Fetch a single agenda item with full detail for the item detail page.
 * Looks up by meeting ID + case-insensitive item_number (human-readable URL).
 */
export async function getAgendaItemDetail(
  meetingId: string,
  itemNumber: string,
  cityFips = RICHMOND_FIPS
): Promise<AgendaItemDetail | null> {
  // 1. Fetch item + meeting context
  const { data: itemRow, error: itemError } = await supabase
    .from('agenda_items')
    .select('*, meetings!inner(meeting_date, meeting_type, agenda_url, minutes_url, city_fips)')
    .eq('meeting_id', meetingId)
    .eq('meetings.city_fips', cityFips)
    .ilike('item_number', itemNumber)
    .single()

  if (itemError || !itemRow) return null

  const meeting = itemRow.meetings as unknown as {
    meeting_date: string
    meeting_type: string
    agenda_url: string | null
    minutes_url: string | null
  }
  const item = itemRow as unknown as AgendaItem

  // 2. Fetch motions + votes
  const { data: motions } = await supabase
    .from('motions')
    .select('*')
    .eq('agenda_item_id', item.id)
    .order('sequence_number')

  const motionIds = (motions ?? []).map((m) => m.id as string)
  const { data: votes } = await supabase
    .from('votes')
    .select('*')
    .in('motion_id', motionIds.length > 0 ? motionIds : ['__none__'])

  const votesByMotion = new Map<string, Vote[]>()
  for (const v of (votes ?? []) as Vote[]) {
    const arr = votesByMotion.get(v.motion_id) ?? []
    arr.push(v)
    votesByMotion.set(v.motion_id, arr)
  }

  const motionsWithVotes: MotionWithVotes[] = ((motions ?? []) as Motion[]).map((m) => ({
    ...m,
    votes: votesByMotion.get(m.id) ?? [],
  }))

  // 3. Fetch full public comments
  const { data: commentRows } = await supabase
    .from('public_comments')
    .select('id, speaker_name, method, comment_type, summary')
    .eq('agenda_item_id', item.id)
    .order('created_at')

  // 4. Notable speaker detection
  const allOfficials = await getOfficials(cityFips)
  const officialNameMap = new Map(
    allOfficials.map((o) => [o.name.toLowerCase(), o])
  )

  let spokenCount = 0
  let writtenCount = 0
  const comments: PublicCommentDetail[] = (commentRows ?? []).map((c) => {
    const commentType = c.comment_type as string
    if (commentType === 'written') writtenCount++
    else spokenCount++

    const official = officialNameMap.get((c.speaker_name as string).toLowerCase())
    return {
      id: c.id as string,
      speaker_name: c.speaker_name as string,
      method: c.method as string,
      comment_type: commentType,
      summary: c.summary as string | null,
      is_notable: !!official,
      notable_role: official
        ? (official.is_current
            ? official.role.replace(/_/g, ' ')
            : `former ${official.role.replace(/_/g, ' ')}`)
        : undefined,
    }
  })

  // 5. Conflict flags at publication threshold
  const { data: flags } = await supabase
    .from('conflict_flags')
    .select('*')
    .eq('agenda_item_id', item.id)
    .eq('is_current', true)
    .gte('confidence', CONFIDENCE_PUBLISHED)

  // 6. Resolve continued_from/to references
  const resolveRef = async (refNumber: string | null): Promise<AgendaItemRef | null> => {
    if (!refNumber) return null
    const { data: refItem } = await supabase
      .from('agenda_items')
      .select('id, meeting_id, item_number, title, meetings!inner(meeting_date)')
      .ilike('item_number', refNumber)
      .eq('meetings.city_fips', cityFips)
      .neq('meeting_id', meetingId)
      .order('meetings(meeting_date)', { ascending: false })
      .limit(1)
      .single()
    if (!refItem) return null
    const refMeeting = refItem.meetings as unknown as { meeting_date: string }
    return {
      id: refItem.id as string,
      meeting_id: refItem.meeting_id as string,
      item_number: refItem.item_number as string,
      title: refItem.title as string,
      meeting_date: refMeeting.meeting_date,
    }
  }

  // 7. Sibling items for prev/next navigation
  const { data: siblings } = await supabase
    .from('agenda_items')
    .select('item_number, summary_headline, title')
    .eq('meeting_id', meetingId)
    .order('item_number')

  let prevItem: AgendaItemSibling | null = null
  let nextItem: AgendaItemSibling | null = null
  if (siblings) {
    const idx = siblings.findIndex(
      (s) => (s.item_number as string).toLowerCase() === item.item_number.toLowerCase()
    )
    if (idx > 0) {
      const s = siblings[idx - 1]
      prevItem = { item_number: s.item_number as string, summary_headline: s.summary_headline as string | null, title: s.title as string }
    }
    if (idx >= 0 && idx < siblings.length - 1) {
      const s = siblings[idx + 1]
      nextItem = { item_number: s.item_number as string, summary_headline: s.summary_headline as string | null, title: s.title as string }
    }
  }

  // 8. Related items by topic label
  let relatedTopicItems: RelatedTopicItem[] = []
  if (item.topic_label) {
    const { data: topicRows } = await supabase
      .from('agenda_items')
      .select('id, meeting_id, item_number, title, summary_headline, topic_label, meetings!inner(meeting_date, city_fips, minutes_url)')
      .eq('meetings.city_fips', cityFips)
      .eq('topic_label', item.topic_label)
      .neq('id', item.id)
      .order('meetings(meeting_date)', { ascending: false })
      .limit(10)

    if (topicRows) {
      // Fetch motions for these items to determine vote outcome
      const relIds = topicRows.map((r) => r.id as string)
      const { data: relMotions } = await supabase
        .from('motions')
        .select('agenda_item_id, result')
        .in('agenda_item_id', relIds.length > 0 ? relIds : ['__none__'])

      const motionMap = new Map<string, string>()
      for (const m of relMotions ?? []) {
        // Take the last motion result (highest priority)
        motionMap.set(m.agenda_item_id as string, m.result as string)
      }

      const today = new Date().toISOString().slice(0, 10)
      relatedTopicItems = topicRows.map((r) => {
        const mtg = r.meetings as unknown as { meeting_date: string; minutes_url: string | null }
        const motionResult = motionMap.get(r.id as string)
        let voteOutcome: RelatedTopicItem['vote_outcome']
        if (mtg.meeting_date > today) {
          voteOutcome = 'upcoming'
        } else if (!motionResult && !mtg.minutes_url) {
          voteOutcome = 'minutes pending'
        } else if (!motionResult) {
          voteOutcome = 'no vote'
        } else if (motionResult.toLowerCase().includes('pass') || motionResult.toLowerCase().includes('approv') || motionResult.toLowerCase().includes('adopt')) {
          voteOutcome = 'passed'
        } else {
          voteOutcome = 'failed'
        }
        return {
          id: r.id as string,
          meeting_id: r.meeting_id as string,
          item_number: r.item_number as string,
          title: r.title as string,
          summary_headline: r.summary_headline as string | null,
          topic_label: r.topic_label as string,
          meeting_date: mtg.meeting_date,
          vote_outcome: voteOutcome,
        }
      })

      // Sort: upcoming first, then by date descending
      relatedTopicItems.sort((a, b) => {
        if (a.vote_outcome === 'upcoming' && b.vote_outcome !== 'upcoming') return -1
        if (b.vote_outcome === 'upcoming' && a.vote_outcome !== 'upcoming') return 1
        return b.meeting_date.localeCompare(a.meeting_date)
      })
    }
  }

  // Build comment summary for the base type
  const notableSpeakers: NotableSpeaker[] = []
  for (const c of comments) {
    if (c.is_notable && c.notable_role && !notableSpeakers.some(n => n.name === c.speaker_name)) {
      notableSpeakers.push({ name: c.speaker_name, role: c.notable_role })
    }
  }

  return {
    ...item,
    motions: motionsWithVotes,
    public_comment_count: comments.length,
    comment_summary: comments.length > 0
      ? { total: comments.length, notable_speakers: notableSpeakers }
      : undefined,
    meeting_date: meeting.meeting_date,
    meeting_type: meeting.meeting_type,
    meeting_agenda_url: meeting.agenda_url,
    meeting_minutes_url: meeting.minutes_url,
    comments,
    written_comment_count: writtenCount,
    spoken_comment_count: spokenCount,
    conflict_flags: (flags ?? []) as ConflictFlag[],
    continued_from_item: await resolveRef(item.continued_from),
    continued_to_item: await resolveRef(item.continued_to),
    prev_item: prevItem,
    next_item: nextItem,
    related_topic_items: relatedTopicItems,
  }
}

/**
 * Lightweight query for sitemap generation — just IDs and item numbers.
 */
export async function getAgendaItemSlugs(
  cityFips = RICHMOND_FIPS
): Promise<{ meeting_id: string; item_number: string; meeting_date: string }[]> {
  const { data } = await supabase
    .from('agenda_items')
    .select('meeting_id, item_number, meetings!inner(meeting_date, city_fips)')
    .eq('meetings.city_fips', cityFips)

  if (!data) return []

  return data.map((row) => {
    const meeting = row.meetings as unknown as { meeting_date: string }
    return {
      meeting_id: row.meeting_id as string,
      item_number: row.item_number as string,
      meeting_date: meeting.meeting_date,
    }
  })
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
    .select('id, official_id')
    .eq('city_fips', cityFips)
    .not('official_id', 'is', null)

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
