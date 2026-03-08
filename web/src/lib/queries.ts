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
  AgendaItemWithMotions,
  MotionWithVotes,
  MeetingDetail,
  DonorAggregate,
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
  FinancialConnectionFlag,
  OfficialConnectionSummary,
} from './types'
import { CONFIDENCE_PUBLISHED } from './thresholds'

const RICHMOND_FIPS = '0660620'

// ─── Meetings ────────────────────────────────────────────────

export async function getMeetings(cityFips = RICHMOND_FIPS) {
  const { data, error } = await supabase
    .from('meetings')
    .select('*')
    .eq('city_fips', cityFips)
    .order('meeting_date', { ascending: false })

  if (error) throw error
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
  }

  const countMap = new Map(
    ((counts ?? []) as MeetingCounts[]).map((c) => [c.meeting_id, c])
  )

  return meetings.map((m) => {
    const c = countMap.get(m.id)
    const allCats = c?.categories ?? []
    return {
      ...m,
      agenda_item_count: Number(c?.agenda_item_count ?? 0),
      vote_count: Number(c?.vote_count ?? 0),
      top_categories: allCats.slice(0, 4),
      all_categories: allCats,
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

  const agendaItems: AgendaItemWithMotions[] = ((items ?? []) as AgendaItem[]).map((i) => ({
    ...i,
    motions: motionsByItem.get(i.id) ?? [],
  }))

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
  if (error) throw error
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

  if (error) throw error
  return data ?? []
}

export async function getTopDonors(
  officialId: string,
  limit = 20,
  cityFips = RICHMOND_FIPS
): Promise<DonorAggregate[]> {
  // Find committees linked to this official
  const { data: committees } = await supabase
    .from('committees')
    .select('id')
    .eq('official_id', officialId)
    .eq('city_fips', cityFips)

  const committeeIds = (committees ?? []).map((c) => c.id)
  if (committeeIds.length === 0) return []

  // Get contributions to those committees, aggregated by donor
  const { data, error } = await supabase
    .from('contributions')
    .select('amount, source, donors!inner(name, employer, donor_pattern)')
    .in('committee_id', committeeIds)
    .eq('city_fips', cityFips)

  if (error) throw error

  // Aggregate by donor name, filtering out government entities that
  // appear in filings but are not actual campaign donors
  const donorMap = new Map<string, DonorAggregate>()
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

    const key = donor.name
    const existing = donorMap.get(key)
    if (existing) {
      existing.total_amount += row.amount as number
      existing.contribution_count += 1
    } else {
      donorMap.set(key, {
        donor_name: donor.name,
        donor_employer: donor.employer,
        total_amount: row.amount as number,
        contribution_count: 1,
        source: row.source as string,
        donor_pattern: donor.donor_pattern,
      })
    }
  }

  return Array.from(donorMap.values())
    .sort((a, b) => b.total_amount - a.total_amount)
    .slice(0, limit)
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

  if (error) throw error

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

  if (error) throw error

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

  return {
    meetings: meetings.count ?? 0,
    agendaItems: items.count ?? 0,
    votes: votes.count ?? 0,
    contributions: contributions.count ?? 0,
    conflictFlags: flags.count ?? 0,
  }
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
  if (error) throw error
  return data as ConflictFlag[]
}

// ─── Attendance ──────────────────────────────────────────────

export async function getAttendance(meetingId: string) {
  const { data, error } = await supabase
    .from('meeting_attendance')
    .select('*, officials(name, role)')
    .eq('meeting_id', meetingId)

  if (error) throw error
  return data ?? []
}

// ─── Reports ────────────────────────────────────────────────

export async function getMeetingsWithFlags(cityFips = RICHMOND_FIPS) {
  // Get all conflict flags grouped by meeting
  const { data: flags, error } = await supabase
    .from('conflict_flags')
    .select('meeting_id, confidence')
    .eq('city_fips', cityFips)
    .eq('is_current', true)

  if (error) throw error

  // Group flags by meeting_id and count published vs total
  const meetingFlagMap = new Map<string, { total: number; published: number }>()
  for (const f of flags ?? []) {
    if (!f.meeting_id) continue
    const existing = meetingFlagMap.get(f.meeting_id) ?? { total: 0, published: 0 }
    existing.total += 1
    if (f.confidence >= CONFIDENCE_PUBLISHED) existing.published += 1
    meetingFlagMap.set(f.meeting_id, existing)
  }

  if (meetingFlagMap.size === 0) return []

  // Fetch those meetings
  const meetingIds = Array.from(meetingFlagMap.keys())
  const { data: meetings } = await supabase
    .from('meetings')
    .select('*')
    .in('id', meetingIds)
    .order('meeting_date', { ascending: false })

  // Also get agenda item counts for "items scanned"
  const { data: itemCounts } = await supabase
    .from('agenda_items')
    .select('meeting_id')
    .in('meeting_id', meetingIds)

  const itemCountMap = new Map<string, number>()
  for (const item of itemCounts ?? []) {
    itemCountMap.set(item.meeting_id, (itemCountMap.get(item.meeting_id) ?? 0) + 1)
  }

  return (meetings ?? []).map((m) => ({
    ...(m as Meeting),
    items_scanned: itemCountMap.get(m.id) ?? 0,
    flags_total: meetingFlagMap.get(m.id)?.total ?? 0,
    flags_published: meetingFlagMap.get(m.id)?.published ?? 0,
  }))
}

export async function getConflictFlagsDetailed(meetingId: string, cityFips = RICHMOND_FIPS) {
  const { data, error } = await supabase
    .from('conflict_flags')
    .select('*, agenda_items(title, item_number, category), officials(name)')
    .eq('meeting_id', meetingId)
    .eq('city_fips', cityFips)
    .eq('is_current', true)
    .order('confidence', { ascending: false })

  if (error) throw error
  return (data ?? []).map((f) => ({
    ...(f as unknown as ConflictFlag),
    agenda_item_title: (f.agenda_items as { title: string; item_number: string; category: string | null } | null)?.title ?? null,
    agenda_item_number: (f.agenda_items as { title: string; item_number: string; category: string | null } | null)?.item_number ?? null,
    agenda_item_category: (f.agenda_items as { title: string; item_number: string; category: string | null } | null)?.category ?? null,
    official_name: (f.officials as { name: string } | null)?.name ?? null,
  }))
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
    official_slug: officialName.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, ''),
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

  if (flagError) throw flagError
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
    if (voteError) throw voteError
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

  if (error) throw error
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
  const now = new Date()
  const overdue = requests.filter((r) => {
    if (r.status === 'Completed' || r.status === 'closed') return false
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

  if (error) throw error

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

  if (error) throw error
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

  if (error) throw error

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

  if (error) throw error
  return (data ?? []) as CommissionStaleness[]
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
function parseVoteTally(tally: string | null): { ayes: number; nays: number } | null {
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

/**
 * Compute controversy score for a single item.
 * Formula: split_vote_weight * 6 + comment_weight * 3 + multiple_motions * 1
 */
function computeControversyScore(
  voteTally: string | null,
  publicCommentCount: number,
  meetingMaxComments: number,
  motionCount: number,
  isConsentCalendar: boolean,
): number {
  // Consent calendar items not pulled for separate vote = 0
  if (isConsentCalendar) return 0

  const parsed = parseVoteTally(voteTally)
  if (!parsed) return 0

  const { ayes, nays } = parsed
  const total = ayes + nays
  if (total === 0) return 0

  // Split vote weight: 1 - |ayes - nays| / total
  const splitWeight = 1 - Math.abs(ayes - nays) / total

  // Comment weight: normalized against meeting max
  const commentWeight = meetingMaxComments > 0
    ? publicCommentCount / meetingMaxComments
    : 0

  // Multiple motions weight
  const multipleMotions = motionCount > 1 ? 1 : 0

  return Math.round((splitWeight * 6 + commentWeight * 3 + multipleMotions * 1) * 10) / 10
}

/**
 * Get category-level statistics for council time-spent analysis.
 */
export async function getCategoryStats(
  cityFips = RICHMOND_FIPS
): Promise<CategoryStats[]> {
  // Use !inner join to filter agenda items by city through meetings (server-side)
  // Avoids passing 700+ meeting UUIDs as URL parameters which exceeds PostgREST limits
  const { data: items, error: itemsError } = await supabase
    .from('agenda_items')
    .select(`
      id, category, is_consent_calendar, meeting_id,
      meetings!inner (city_fips),
      motions (id, result, vote_tally)
    `)
    .eq('meetings.city_fips', cityFips)

  if (itemsError) throw itemsError
  const cityItems = items ?? []

  // Fetch public comment counts per agenda item (batched to avoid URL length limits)
  const itemIds = cityItems.map((i) => i.id)
  const allComments: Array<{ agenda_item_id: string | null }> = []
  for (let i = 0; i < itemIds.length; i += 300) {
    const chunk = itemIds.slice(i, i + 300)
    const { data: comments } = await supabase
      .from('public_comments')
      .select('agenda_item_id')
      .in('agenda_item_id', chunk)
      .not('agenda_item_id', 'is', null)
    allComments.push(...(comments ?? []))
  }

  const commentCountMap = new Map<string, number>()
  for (const c of allComments) {
    if (c.agenda_item_id) {
      commentCountMap.set(c.agenda_item_id, (commentCountMap.get(c.agenda_item_id) ?? 0) + 1)
    }
  }

  // Aggregate by category
  const totalItems = cityItems.length
  const categoryMap = new Map<string, {
    item_count: number
    vote_count: number
    split_vote_count: number
    unanimous_vote_count: number
    controversy_scores: number[]
    total_public_comments: number
  }>()

  for (const item of cityItems) {
    const cat = item.category ?? 'other'
    const entry = categoryMap.get(cat) ?? {
      item_count: 0,
      vote_count: 0,
      split_vote_count: 0,
      unanimous_vote_count: 0,
      controversy_scores: [],
      total_public_comments: 0,
    }

    entry.item_count += 1
    const commentCount = commentCountMap.get(item.id) ?? 0
    entry.total_public_comments += commentCount

    const motions = (item as Record<string, unknown>).motions as Array<{
      id: string
      result: string
      vote_tally: string | null
    }> ?? []

    entry.vote_count += motions.length

    for (const motion of motions) {
      const parsed = parseVoteTally(motion.vote_tally)
      if (parsed) {
        if (parsed.nays === 0) {
          entry.unanimous_vote_count += 1
        } else {
          entry.split_vote_count += 1
        }
      }
    }

    // Compute controversy score for the item (use 1 as meetingMax placeholder, will normalize later)
    const score = computeControversyScore(
      motions[0]?.vote_tally ?? null,
      commentCount,
      1, // per-item scoring; meeting-level normalization happens in getControversialItems
      motions.length,
      item.is_consent_calendar as boolean,
    )
    entry.controversy_scores.push(score)

    categoryMap.set(cat, entry)
  }

  return Array.from(categoryMap.entries())
    .map(([category, data]) => ({
      category,
      item_count: data.item_count,
      vote_count: data.vote_count,
      split_vote_count: data.split_vote_count,
      unanimous_vote_count: data.unanimous_vote_count,
      avg_controversy_score: data.controversy_scores.length > 0
        ? Math.round((data.controversy_scores.reduce((a, b) => a + b, 0) / data.controversy_scores.length) * 10) / 10
        : 0,
      max_controversy_score: data.controversy_scores.length > 0
        ? Math.max(...data.controversy_scores)
        : 0,
      total_public_comments: data.total_public_comments,
      percentage_of_agenda: totalItems > 0
        ? Math.round((data.item_count / totalItems) * 1000) / 10
        : 0,
    }))
    .sort((a, b) => b.item_count - a.item_count)
}

/**
 * Get the most controversial agenda items across all meetings.
 */
export async function getControversialItems(
  limit = 20,
  cityFips = RICHMOND_FIPS
): Promise<ControversyItem[]> {
  // Use !inner join to scope by city and get meeting_date in one query
  const { data: items, error } = await supabase
    .from('agenda_items')
    .select(`
      id, meeting_id, item_number, title, category, is_consent_calendar,
      meetings!inner (city_fips, meeting_date),
      motions (id, result, vote_tally)
    `)
    .eq('meetings.city_fips', cityFips)
    .eq('is_consent_calendar', false)

  if (error) throw error

  const cityItems = items ?? []

  // Build meeting_date lookup from the joined data
  const meetingDateMap = new Map<string, string>()
  for (const item of cityItems) {
    const meeting = (item as Record<string, unknown>).meetings as { city_fips: string; meeting_date: string } | null
    if (meeting && !meetingDateMap.has(item.meeting_id as string)) {
      meetingDateMap.set(item.meeting_id as string, meeting.meeting_date)
    }
  }

  // Get public comment counts (batched to avoid URL length limits)
  const itemIds = cityItems.map((i) => i.id)
  const allComments: Array<{ agenda_item_id: string | null }> = []
  for (let i = 0; i < itemIds.length; i += 300) {
    const chunk = itemIds.slice(i, i + 300)
    const { data: comments } = await supabase
      .from('public_comments')
      .select('agenda_item_id')
      .in('agenda_item_id', chunk)
      .not('agenda_item_id', 'is', null)
    allComments.push(...(comments ?? []))
  }

  const commentCountMap = new Map<string, number>()
  for (const c of allComments) {
    if (c.agenda_item_id) {
      commentCountMap.set(c.agenda_item_id, (commentCountMap.get(c.agenda_item_id) ?? 0) + 1)
    }
  }

  // Find max comments per meeting for normalization
  const meetingMaxComments = new Map<string, number>()
  for (const item of cityItems) {
    const count = commentCountMap.get(item.id) ?? 0
    const current = meetingMaxComments.get(item.meeting_id) ?? 0
    if (count > current) meetingMaxComments.set(item.meeting_id, count)
  }

  // Score all items
  const scored: ControversyItem[] = cityItems
    .map((item) => {
      const motions = (item as Record<string, unknown>).motions as Array<{
        id: string
        result: string
        vote_tally: string | null
      }> ?? []
      const commentCount = commentCountMap.get(item.id) ?? 0
      const maxComments = meetingMaxComments.get(item.meeting_id) ?? 1

      const score = computeControversyScore(
        motions[0]?.vote_tally ?? null,
        commentCount,
        maxComments,
        motions.length,
        item.is_consent_calendar as boolean,
      )

      return {
        agenda_item_id: item.id as string,
        meeting_id: item.meeting_id as string,
        meeting_date: meetingDateMap.get(item.meeting_id) ?? '',
        item_number: item.item_number as string,
        title: item.title as string,
        category: item.category as string | null,
        controversy_score: score,
        vote_tally: motions[0]?.vote_tally ?? null,
        result: motions[0]?.result ?? 'unknown',
        public_comment_count: commentCount,
        motion_count: motions.length,
      }
    })
    .filter((item) => item.controversy_score > 0)
    .sort((a, b) => b.controversy_score - a.controversy_score)
    .slice(0, limit)

  return scored
}

// ─── Coalition / Voting Alignment (S6.1) ────────────────────

/**
 * Fetch all individual votes for a city, joined to motions/agenda_items for category.
 * Returns a flat list suitable for pairwise alignment computation.
 */
async function fetchVotesForAlignment(cityFips = RICHMOND_FIPS) {
  // Use nested !inner joins to filter votes by city through motions → agenda_items → meetings
  // This filters server-side instead of fetching all votes and filtering client-side
  const { data: votes, error } = await supabase
    .from('votes')
    .select(`
      id,
      motion_id,
      official_id,
      official_name,
      vote_choice,
      motions!inner (
        id,
        agenda_items!inner (
          id,
          meeting_id,
          category,
          meetings!inner (
            city_fips
          )
        )
      )
    `)
    .not('official_id', 'is', null)
    .in('vote_choice', ['aye', 'nay'])
    .eq('motions.agenda_items.meetings.city_fips', cityFips)

  if (error) throw error

  return votes ?? []
}

/**
 * Compute pairwise alignment between all council members.
 * Returns overall alignment and per-category breakdowns.
 */
export async function getCoalitionData(cityFips = RICHMOND_FIPS): Promise<{
  alignments: PairwiseAlignment[]
  blocs: VotingBloc[]
  divergences: CategoryDivergence[]
  officials: Array<{ id: string; name: string }>
}> {
  const votes = await fetchVotesForAlignment(cityFips)

  // Group votes by motion_id: { motion_id -> [{ official_id, official_name, vote_choice, category }] }
  const votesByMotion = new Map<string, Array<{
    official_id: string
    official_name: string
    vote_choice: string
    category: string | null
  }>>()

  type MotionWithItem = { id: string; agenda_items: { id: string; meeting_id: string; category: string | null } }

  for (const v of votes) {
    const motion = v.motions as unknown as MotionWithItem
    const motionId = v.motion_id as string
    const entry = votesByMotion.get(motionId) ?? []
    entry.push({
      official_id: v.official_id as string,
      official_name: v.official_name as string,
      vote_choice: v.vote_choice as string,
      category: motion.agenda_items.category,
    })
    votesByMotion.set(motionId, entry)
  }

  // Filter to contested motions only (both aye and nay present).
  // Unanimous votes wash out political signal — blocs and divergences
  // only emerge when council members actually disagree.
  for (const [motionId, motionVotes] of votesByMotion) {
    const choices = new Set(motionVotes.map((v) => v.vote_choice))
    if (!choices.has('aye') || !choices.has('nay')) {
      votesByMotion.delete(motionId)
    }
  }

  // Collect all unique officials
  const officialMap = new Map<string, string>()
  for (const v of votes) {
    officialMap.set(v.official_id as string, v.official_name as string)
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
 * Brute-force clique finding (fine for 7 members).
 */
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

  const blocs: VotingBloc[] = []
  const ids = officials.map((o) => o.id)

  // Check all subsets of size 3+
  for (let size = ids.length; size >= 3; size--) {
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
