import { readCompleteRecords } from '../complete-record-read'
import { failReadPath } from '../read-path-unavailable'
import {
  supabase,
  RICHMOND_FIPS,
  filterGovernmentEntityFlags,
  COLS_MEETING_LIST,
  COLS_MEETING_BANNER,
} from './_shared'
import { isUuid } from '../uuid'
import { cache } from 'react'
import type {
  Meeting,
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
  CategoryCount,
  TopicLabelCount,
  PublicCommentDetail,
  CommentTheme,
  ThemeNarrative,
  AgendaItemDetail,
  AgendaItemSibling,
} from '../types'
import { getOfficials } from './council'

// ─── Meetings ────────────────────────────────────────────────

/** Get the next upcoming meeting (for banner/CTA). */
export async function getNextMeeting(
  cityFips = RICHMOND_FIPS,
): Promise<Meeting | null> {
  const today = new Date().toISOString().split('T')[0]
  const { data, error } = await supabase
    .from('meetings')
    .select(COLS_MEETING_BANNER)
    .eq('city_fips', cityFips)
    .gte('meeting_date', today)
    .order('meeting_date', { ascending: true })
    .limit(1)
    .single()

  if (error || !data) return null
  return data as Meeting
}

export async function getMeetings(cityFips = RICHMOND_FIPS) {
  return await readCompleteRecords('Meeting index', (from, to) => supabase.from('meetings')
    .select(COLS_MEETING_LIST, { count: 'exact' }).eq('city_fips', cityFips)
    .order('meeting_date', { ascending: false }).order('id').range(from, to)) as Meeting[]
}

interface MeetingCounts {
  meeting_id: string
  agenda_item_count: number
  vote_count: number
  categories: CategoryCount[]
  topic_labels: TopicLabelCount[]
}

/** One complete invoker-RLS source for item, motion-with-vote and category counts.
 * Migration 064 returns every visible meeting, including explicit zero rows.
 * Migration 133's RLS excludes cancelled meetings and retired agenda entries.
 */
export async function fetchMeetingCounts(cityFips: string): Promise<Map<string, MeetingCounts>> {
  const counts = await readCompleteRecords('Meeting counts', async (from, to) => {
    const page = await supabase.rpc('get_meeting_counts', { p_city_fips: cityFips }, { count: 'exact' })
      .order('meeting_id').range(from, to)
    return { ...page, data: page.data === null ? null : (page.data as MeetingCounts[]).map(row => ({ ...row, id: row.meeting_id })) }
  })
  const validCount = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
  const validGroups = (groups: unknown, key: 'category' | 'label', itemCount: number): boolean => {
    if (!Array.isArray(groups)) return false
    const names = new Set<string>()
    let sum = 0
    for (const entry of groups as unknown[]) {
      if (!entry || typeof entry !== 'object') return false
      const group = entry as Record<string, unknown>
      const name = group[key]
      const count = group.count
      if (typeof name !== 'string' || !name.trim() || names.has(name) || !validCount(count) || count === 0) return false
      names.add(name)
      sum += count
      if (!Number.isSafeInteger(sum) || sum > itemCount) return false
    }
    return true
  }
  return new Map(counts.map(row => {
    if (!validCount(row.agenda_item_count) || !validCount(row.vote_count)
      || !validGroups(row.categories, 'category', row.agenda_item_count)
      || !validGroups(row.topic_labels, 'label', row.agenda_item_count)) {
      failReadPath('Meeting counts', 'Invalid source count or category rows')
    }
    return [row.meeting_id, { meeting_id: row.meeting_id, agenda_item_count: row.agenda_item_count,
      vote_count: row.vote_count, categories: row.categories, topic_labels: row.topic_labels }]
  }))
}

/** Use the same checked RPC row for every displayed count; absence is not zero. */
export function applyMeetingCounts(meetings: Meeting[], countMap: Map<string, MeetingCounts>) {
  return meetings.map((m) => {
    const c = countMap.get(m.id)
    if (!c) failReadPath('Meeting counts', 'A visible meeting has no source count row')
    const allCats = c.categories
    const allLabels = c.topic_labels
    return {
      ...m,
      agenda_item_count: c.agenda_item_count,
      vote_count: c.vote_count,
      top_categories: allCats.slice(0, 4),
      all_categories: allCats,
      top_topic_labels: allLabels.slice(0, 5),
      all_topic_labels: allLabels,
    }
  })
}

export async function getMeetingsWithCounts(cityFips = RICHMOND_FIPS) {
  const [meetings, countMap] = await Promise.all([
    getMeetings(cityFips),
    fetchMeetingCounts(cityFips),
  ])

  return applyMeetingCounts(meetings, countMap)
}

export const getMeeting = cache(async function getMeeting(
  meetingId: string,
): Promise<MeetingDetail | null> {
  if (!isUuid(meetingId)) return null

  // Fetch meeting
  const { data: meeting, error } = await supabase
    .from('meetings')
    .select('*, bodies(name)')
    .eq('id', meetingId)
    .maybeSingle()

  if (error) failReadPath('Meeting', error)
  if (!meeting) return null

  // Each displayed count and list uses the same complete source rows.
  const [items, attendance, closedSession, commentRows] = await Promise.all([
    readCompleteRecords('Meeting agenda', (from, to) => supabase.from('agenda_items')
      .select('*', { count: 'exact' }).is('agenda_source_retired_at', null).eq('meeting_id', meetingId)
      .order('item_number').order('id').range(from, to)),
    readCompleteRecords('Meeting attendance records', (from, to) => supabase.from('meeting_attendance')
      .select('*, officials(name, role)', { count: 'exact' }).eq('meeting_id', meetingId).order('id').range(from, to)),
    readCompleteRecords('Closed session records', (from, to) => supabase.from('closed_session_items')
      .select('*', { count: 'exact' }).eq('meeting_id', meetingId).order('id').range(from, to)),
    readCompleteRecords('Meeting comment records', (from, to) => supabase.from('public_comments')
      .select('id, agenda_item_id, speaker_name, comment_type, method, source', { count: 'exact' })
      .eq('meeting_id', meetingId).order('id').range(from, to)),
  ])
  const itemIds = items.map(item => item.id)
  const motions = itemIds.length ? await readCompleteRecords('Meeting motions', (from, to) => supabase.from('motions')
    .select('*', { count: 'exact' }).in('agenda_item_id', itemIds).order('sequence_number').order('id').range(from, to)) : []
  const motionIds = motions.map(motion => motion.id)
  const votes = motionIds.length ? await readCompleteRecords('Meeting vote records', (from, to) => supabase.from('votes')
    .select('*', { count: 'exact' }).in('motion_id', motionIds).order('id').range(from, to)) : []

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

  const agendaItems: AgendaItemWithMotions[] = (items as AgendaItem[]).map((item) => ({
    ...item,
    motions: motionsByItem.get(item.id) ?? [],
  }))

  const attendanceWithOfficials = (attendance ?? []).map((a) => {
    const official = (a as Record<string, unknown>).officials as { name: string; role: string } | null
    return {
      id: a.id as string,
      meeting_id: a.meeting_id as string,
      official_id: a.official_id as string,
      body_id: (a as Record<string, unknown>).body_id as string | null,
      status: a.status as MeetingAttendance['status'],
      notes: a.notes as string | null,
      official: official ?? { name: 'Unknown', role: 'unknown' },
    }
  })

  const meetingBody = (meeting as unknown as {
    bodies: { name: string } | null
  }).bodies

  return {
    ...(meeting as Meeting),
    body_name: meetingBody?.name ?? null,
    agenda_items: agendaItems,
    attendance: attendanceWithOfficials,
    closed_session_items: (closedSession ?? []) as ClosedSessionItem[],
    total_public_comments: commentRows.length,
  }
})


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
      .select(COLS_MEETING_LIST)
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

export async function getConflictFlagsDetailed(meetingId: string, cityFips = RICHMOND_FIPS, client = supabase) {
  const { data, error } = await client
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
    .select('id, meeting_date, agenda_item_count')
    .eq('id', meetingId)
    .single()

  if (error || !meeting) return null

  return {
    id: meeting.id as string,
    meeting_date: meeting.meeting_date as string,
    agenda_item_count: (meeting.agenda_item_count as number) ?? 0,
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


// ─── Agenda Item Detail Page ────────────────────────────────

/**
 * Fetch a single agenda item with full detail for the item detail page.
 * Looks up by meeting ID + case-insensitive item_number (human-readable URL).
 */
export const getAgendaItemDetail = cache(async function getAgendaItemDetail(
  meetingId: string,
  itemNumber: string,
  cityFips = RICHMOND_FIPS
): Promise<AgendaItemDetail | null> {
  if (!isUuid(meetingId)) return null

  // 1. Fetch item + meeting context
  const { data: itemRow, error: itemError } = await supabase
    .from('agenda_items')
    .select('*, meetings!inner(meeting_date, meeting_type, agenda_url, minutes_url, city_fips)')
    .is('agenda_source_retired_at', null)
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

  // Motions and comments are independent once the item is known.
  const [{ data: motions }, { data: commentRows }] = await Promise.all([
    supabase
      .from('motions')
      .select('*')
      .eq('agenda_item_id', item.id)
      .order('sequence_number'),
    supabase
      .from('public_comments')
      .select('id, speaker_name, method, comment_type, summary, source, extracted_at')
      .eq('agenda_item_id', item.id)
      .order('created_at'),
  ])

  const motionIds = (motions ?? []).map((m) => m.id as string)
  const commentIds = (commentRows ?? []).map((c) => c.id as string)
  const [votesResult, narrativeResult, assignmentResult] = await Promise.all([
    motionIds.length > 0
      ? supabase.from('votes').select('*').in('motion_id', motionIds)
      : Promise.resolve({ data: [] }),
    supabase.from('item_theme_narratives')
      .select('narrative, comment_count, confidence, generated_at, comment_themes(id, slug, label, description)')
      .eq('agenda_item_id', item.id)
      .order('comment_count', { ascending: false }),
    commentIds.length > 0
      ? supabase.from('comment_theme_assignments')
          .select('comment_id, confidence, comment_themes(slug)')
          .in('comment_id', commentIds)
      : Promise.resolve({ data: [] }),
  ])
  const votes = votesResult.data
  const narrativeRows = narrativeResult.data
  const assignmentRows = assignmentResult.data

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

  // Build theme assignment lookup: comment_id → { slug, confidence }
  const themeAssignmentMap = new Map<string, { slug: string; confidence: number }>()
  for (const a of assignmentRows ?? []) {
    const theme = a.comment_themes as unknown as { slug: string } | null
    if (theme?.slug) {
      themeAssignmentMap.set(a.comment_id as string, {
        slug: theme.slug,
        confidence: a.confidence as number,
      })
    }
  }

  // Build ThemeNarrative[] from narrative rows
  const themeNarratives: ThemeNarrative[] = (narrativeRows ?? []).map((r) => {
    const theme = r.comment_themes as unknown as CommentTheme
    return {
      theme,
      narrative: r.narrative as string,
      comment_count: r.comment_count as number,
      confidence: r.confidence as number,
      generated_at: r.generated_at as string,
    }
  })

  // Derive comment source metadata from first comment
  const firstComment = commentRows?.[0]
  const commentSource = (firstComment?.source as string | null) ?? null
  const commentExtractedAt = (firstComment?.extracted_at as string | null) ?? null

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
    const themeAssignment = themeAssignmentMap.get(c.id as string)
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
      theme_slug: themeAssignment?.slug,
      theme_confidence: themeAssignment?.confidence,
    }
  })

  // `continued_from` and `continued_to` are extraction-owned descriptive
  // labels (usually dates or phrases such as "future meeting"), not agenda
  // item numbers or foreign keys. Do not turn them into item-number lookups:
  // those reads cannot identify a target and only produce PostgREST 406s.

  // 7. Sibling items for prev/next navigation
  const { data: siblings } = await supabase
    .from('agenda_items')
    .select('item_number, summary_headline, title')
    .is('agenda_source_retired_at', null)
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
    // S20: only use YouTube-sourced count from agenda_items.public_comment_count.
    // Don't fall back to public_comments JOIN (unreliable agenda_item_id linkage).
    public_comment_count: item.public_comment_count ?? 0,
    comment_summary: (item.public_comment_count ?? 0) > 0
      ? { total: item.public_comment_count!, notable_speakers: notableSpeakers }
      : undefined,
    meeting_date: meeting.meeting_date,
    meeting_type: meeting.meeting_type,
    meeting_agenda_url: meeting.agenda_url,
    meeting_minutes_url: meeting.minutes_url,
    comments,
    written_comment_count: writtenCount,
    spoken_comment_count: spokenCount,
    theme_narratives: themeNarratives,
    comment_source: commentSource,
    comment_extracted_at: commentExtractedAt,
    // Operator-only scanner data is fetched through an authenticated endpoint.
    conflict_flags: [],
    // No stable target identity exists for the descriptive continuation labels.
    continued_from_item: null,
    continued_to_item: null,
    prev_item: prevItem,
    next_item: nextItem,
  }
})

/**
 * Lightweight query for sitemap generation — just IDs and item numbers.
 */
export async function getAgendaItemSlugs(
  cityFips = RICHMOND_FIPS
): Promise<{ meeting_id: string; item_number: string; meeting_date: string }[]> {
  const { data } = await supabase
    .from('agenda_items')
    .select('meeting_id, item_number, meetings!inner(meeting_date, city_fips)')
    .is('agenda_source_retired_at', null)
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

