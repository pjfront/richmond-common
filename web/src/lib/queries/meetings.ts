import { readCompleteRecords } from '../complete-record-read'
import { getAgendaMetadata, meetingCards } from './agenda-metadata'
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
  AgendaItemWithMotions,
  MotionWithVotes,
  MeetingDetail,
  PublicCommentDetail,
  AgendaItemDetail,
  AgendaItemSibling,
} from '../types'

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

/** Meeting cards and topics share one complete, source-checked agenda snapshot. */
export async function getMeetingsWithCounts(cityFips = RICHMOND_FIPS) {
  return meetingCards(await getAgendaMetadata(cityFips))
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

  const { data: itemRow, error: itemError } = await supabase
    .from('agenda_items')
    .select('*, meetings!inner(id, meeting_date, meeting_type, agenda_url, minutes_url, city_fips, source_cancelled_at)')
    .is('agenda_source_retired_at', null).is('meetings.source_cancelled_at', null)
    .eq('meeting_id', meetingId).eq('meetings.city_fips', cityFips)
    .ilike('item_number', itemNumber.replace(/[\\%_]/g, '\\$&'))
    .maybeSingle()
  if (itemError) failReadPath('Agenda item', itemError)
  if (!itemRow) return null
  const meeting = itemRow.meetings as unknown as {
    id: string; city_fips: string; source_cancelled_at: string | null;
    meeting_date: string; meeting_type: string; agenda_url: string | null; minutes_url: string | null
  }
  const item = itemRow as unknown as AgendaItem
  if (!meeting || meeting.id !== meetingId || meeting.city_fips !== cityFips || item.meeting_id !== meetingId
    || item.item_number?.toLowerCase() !== itemNumber.toLowerCase()
    || item.agenda_source_retired_at || meeting.source_cancelled_at) {
    failReadPath('Agenda item', 'Item and meeting source identity differ')
  }

  // Counts and visible lists come from complete records, not stored estimates.
  // The optional generated theme/name-match enrichment is intentionally absent.
  const [motions, commentRows, siblings] = await Promise.all([
    readCompleteRecords('Agenda item motions', (from, to) => supabase.from('motions')
      .select('*', { count: 'exact' }).eq('agenda_item_id', item.id)
      .order('sequence_number').order('id').range(from, to), { maxRows: 1000 }),
    readCompleteRecords('Agenda item comment records', (from, to) => supabase.from('public_comments')
      .select('id, agenda_item_id, meeting_id, speaker_name, method, comment_type, summary, source, extracted_at', { count: 'exact' })
      .eq('agenda_item_id', item.id).order('created_at').order('id').range(from, to)),
    readCompleteRecords('Agenda item navigation', (from, to) => supabase.from('agenda_items')
      .select('id, meeting_id, item_number, summary_headline, title', { count: 'exact' })
      .is('agenda_source_retired_at', null).eq('meeting_id', meetingId)
      .order('item_number').order('id').range(from, to)),
  ])
  if (motions.some(motion => motion.agenda_item_id !== item.id)
    || commentRows.some(comment => comment.agenda_item_id !== item.id || comment.meeting_id !== meetingId)
    || siblings.some(sibling => sibling.meeting_id !== meetingId || !sibling.item_number)) {
    failReadPath('Agenda item records', 'A child record belongs to another source')
  }
  const motionIds = motions.map(motion => motion.id)
  const votesByMotion = new Map<string, Vote[]>()
  const seenVotes = new Set<string>()
  for (let offset = 0; offset < motionIds.length; offset += 200) {
    const ids = motionIds.slice(offset, offset + 200)
    const votes = await readCompleteRecords('Agenda item vote records', (from, to) => supabase.from('votes')
      .select('*', { count: 'exact' }).in('motion_id', ids).order('id').range(from, to))
    for (const vote of votes as Vote[]) {
      if (!ids.includes(vote.motion_id) || seenVotes.has(vote.id)) failReadPath('Agenda item vote records', 'Vote source identity differs')
      seenVotes.add(vote.id)
      if (seenVotes.size > 10_000) failReadPath('Agenda item vote records', 'Vote records exceeded their bound')
      const records = votesByMotion.get(vote.motion_id) ?? []
      records.push(vote)
      votesByMotion.set(vote.motion_id, records)
    }
  }
  const motionsWithVotes: MotionWithVotes[] = (motions as Motion[]).map(motion => ({
    ...motion, votes: votesByMotion.get(motion.id) ?? [],
  }))
  const comments: PublicCommentDetail[] = commentRows.map(comment => ({
    id: comment.id as string,
    speaker_name: comment.speaker_name as string,
    method: comment.method as string,
    comment_type: comment.comment_type as string,
    summary: comment.summary as string | null,
    is_notable: false,
  }))
  // These legacy compatibility fields are not used for the displayed count.
  // Unknown or conflicting channel evidence never increments either channel.
  let spokenCount = 0
  let writtenCount = 0
  for (const comment of comments) {
    const method = comment.method?.trim().toLowerCase()
    const type = comment.comment_type?.trim().toLowerCase()
    const spoken = ['in_person', 'zoom', 'phone'].includes(method)
    const written = type === 'written' || ['email', 'ecomment', 'mail'].includes(method)
    if (spoken && !written) spokenCount++
    if (written && !spoken) writtenCount++
  }
  const sources = new Set(commentRows.map(comment => comment.source as string | null))
  const extractionDates = new Set(commentRows.map(comment => comment.extracted_at as string | null))
  // A mixed set cannot inherit one arbitrary first record's provenance.
  const commentSource = sources.size === 1 ? [...sources][0] ?? null : null
  const commentExtractedAt = extractionDates.size === 1 ? [...extractionDates][0] ?? null : null

  const index = siblings.findIndex(sibling => sibling.id === item.id)
  if (index < 0 || siblings[index].item_number.toLowerCase() !== item.item_number.toLowerCase()) {
    failReadPath('Agenda item navigation', 'Selected item is missing or changed in the source list')
  }
  const sibling = (position: number): AgendaItemSibling | null => {
    const row = siblings[position]
    return row ? { item_number: row.item_number, summary_headline: row.summary_headline, title: row.title } : null
  }
  return {
    ...item,
    motions: motionsWithVotes,
    // Keep a nullable legacy estimate as raw data; never promote it to a count
    // or create a comment_summary that competes with the actual record list.
    public_comment_count: item.public_comment_count,
    comment_summary: undefined,
    meeting_date: meeting.meeting_date,
    meeting_type: meeting.meeting_type,
    meeting_agenda_url: meeting.agenda_url,
    meeting_minutes_url: meeting.minutes_url,
    comments,
    written_comment_count: writtenCount,
    spoken_comment_count: spokenCount,
    theme_narratives: [],
    comment_source: commentSource,
    comment_extracted_at: commentExtractedAt,
    conflict_flags: [],
    // Extraction-owned continuation labels are not stable target identities.
    continued_from_item: null,
    continued_to_item: null,
    prev_item: sibling(index - 1),
    next_item: sibling(index + 1),
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

