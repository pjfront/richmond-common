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
  NextRequestRequest,
  PublicRecordsStats,
  DepartmentCompliance,
} from './types'

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
  // Fetch meetings, then count agenda items and votes per meeting
  const meetings = await getMeetings(cityFips)

  const meetingIds = meetings.map((m) => m.id)
  if (meetingIds.length === 0) return []

  const { data: itemCounts } = await supabase
    .from('agenda_items')
    .select('meeting_id')
    .in('meeting_id', meetingIds)

  const { data: voteCounts } = await supabase
    .from('votes')
    .select('motion_id, motions!inner(agenda_item_id, agenda_items!inner(meeting_id))')
    .in('motions.agenda_items.meeting_id', meetingIds)

  // Count per meeting
  const itemCountMap = new Map<string, number>()
  for (const item of itemCounts ?? []) {
    itemCountMap.set(item.meeting_id, (itemCountMap.get(item.meeting_id) ?? 0) + 1)
  }

  // For vote counts, we'll use a simpler approach — count via motions
  const { data: motionsByMeeting } = await supabase
    .from('motions')
    .select('id, agenda_items!inner(meeting_id)')
    .in('agenda_items.meeting_id', meetingIds)

  const motionIds = (motionsByMeeting ?? []).map((m) => m.id)
  const motionToMeeting = new Map<string, string>()
  for (const m of motionsByMeeting ?? []) {
    const meetingId = (m as Record<string, unknown>).agenda_items as { meeting_id: string }
    motionToMeeting.set(m.id, meetingId.meeting_id)
  }

  const { data: allVotes } = await supabase
    .from('votes')
    .select('motion_id')
    .in('motion_id', motionIds.length > 0 ? motionIds : ['__none__'])

  const voteCountMap = new Map<string, number>()
  for (const v of allVotes ?? []) {
    const meetingId = motionToMeeting.get(v.motion_id)
    if (meetingId) {
      voteCountMap.set(meetingId, (voteCountMap.get(meetingId) ?? 0) + 1)
    }
  }

  return meetings.map((m) => ({
    ...m,
    agenda_item_count: itemCountMap.get(m.id) ?? 0,
    vote_count: voteCountMap.get(m.id) ?? 0,
  }))
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

export async function getOfficials(cityFips = RICHMOND_FIPS, currentOnly = false) {
  let query = supabase
    .from('officials')
    .select('*')
    .eq('city_fips', cityFips)
    .order('name')

  if (currentOnly) {
    query = query.eq('is_current', true)
  }

  const { data, error } = await query
  if (error) throw error
  return data as Official[]
}

export async function getOfficialBySlug(slug: string, cityFips = RICHMOND_FIPS) {
  // slug = lowercased, hyphenated name (e.g., "eduardo-martinez")
  const officials = await getOfficials(cityFips)
  return officials.find(
    (o) => o.name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '') === slug
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
    .select('amount, source, donors!inner(name, employer)')
    .in('committee_id', committeeIds)
    .eq('city_fips', cityFips)

  if (error) throw error

  // Aggregate by donor name
  const donorMap = new Map<string, DonorAggregate>()
  for (const row of data ?? []) {
    const donor = (row as Record<string, unknown>).donors as { name: string; employer: string | null }
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
      })
    }
  }

  return Array.from(donorMap.values())
    .sort((a, b) => b.total_amount - a.total_amount)
    .slice(0, limit)
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

  if (error) throw error

  // Group flags by meeting_id and count published vs total
  const meetingFlagMap = new Map<string, { total: number; published: number }>()
  for (const f of flags ?? []) {
    if (!f.meeting_id) continue
    const existing = meetingFlagMap.get(f.meeting_id) ?? { total: 0, published: 0 }
    existing.total += 1
    if (f.confidence >= 0.5) existing.published += 1
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
    .select('*, agenda_items(title, item_number), officials(name)')
    .eq('meeting_id', meetingId)
    .eq('city_fips', cityFips)
    .order('confidence', { ascending: false })

  if (error) throw error
  return (data ?? []).map((f) => ({
    ...(f as unknown as ConflictFlag),
    agenda_item_title: (f.agenda_items as { title: string; item_number: string } | null)?.title ?? null,
    agenda_item_number: (f.agenda_items as { title: string; item_number: string } | null)?.item_number ?? null,
    official_name: (f.officials as { name: string } | null)?.name ?? null,
  }))
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
