import {
  supabase,
  RICHMOND_FIPS,
  warnIfEmpty,
  nameToSlug,
  isGovernmentEntity,
  filterGovernmentEntityFlags,
  COLS_MEETING_LIST,
  COLS_MEETING_BANNER,
  COLS_PUBLIC_RECORD_LIST,
} from './_shared'
import { isUuid } from '../uuid'
import { cache } from 'react'
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
  PublicCommentDetail,
  CommentTheme,
  ThemeNarrative,
  AgendaItemDetail,
  AgendaItemSibling,
  NeighborhoodCouncil,
  Provenance,
  FilingPeriodBriefing,
  PACAggregate,
  PACContributionRow,
  PACOutgoingRow,
  PACIndependentExpenditureRow,
} from '../types'
import { commentSourceToProvenance } from '../provenance'
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
  const { data, error } = await supabase
    .from('meetings')
    .select(COLS_MEETING_LIST)
    .eq('city_fips', cityFips)
    .order('meeting_date', { ascending: false })

  if (error) {
    console.error('getMeetings query failed:', error)
    return [] as Meeting[]
  }
  warnIfEmpty('getMeetings', data)
  return data as Meeting[]
}

interface MeetingCounts {
  meeting_id: string
  agenda_item_count: number
  vote_count: number
  categories: CategoryCount[]
  topic_labels: TopicLabelCount[]
}

/**
 * Fetch meeting counts via RPC with automatic fallback to direct queries.
 * The RPC (get_meeting_counts) is fast but fragile — it gets dropped and
 * recreated across migrations, so any failed migration leaves meetings
 * showing "0 items." The fallback queries agenda_items directly, which
 * always works as long as the base tables exist.
 */
export async function fetchMeetingCounts(cityFips: string): Promise<Map<string, MeetingCounts>> {
  // Try the RPC first (fast, single round-trip for all counts)
  const { data: counts, error: rpcError } = await supabase.rpc('get_meeting_counts', { p_city_fips: cityFips })

  if (!rpcError && counts && (counts as MeetingCounts[]).length > 0) {
    return new Map((counts as MeetingCounts[]).map((c) => [c.meeting_id, c]))
  }

  // RPC failed or returned empty — fall back to direct queries.
  // This is slower (two queries instead of one RPC) but always works.
  console.warn(
    `[Richmond Commons] get_meeting_counts RPC ${rpcError ? 'failed' : 'returned 0 rows'} — falling back to direct count queries.`,
    rpcError ? rpcError.message : ''
  )

  // Fetch all agenda_items with their meeting_id via an inner join on meetings.
  // Supabase PostgREST handles the city_fips filter through the join.
  const { data: itemRows, error: fallbackError } = await supabase
    .from('agenda_items')
    .select('meeting_id, meetings!inner(city_fips)')
    .is('agenda_source_retired_at', null)
    .eq('meetings.city_fips', cityFips)

  if (fallbackError) {
    console.error('[Richmond Commons] Fallback agenda_items count query also failed:', fallbackError.message)
    return new Map<string, MeetingCounts>()
  }

  const map = new Map<string, MeetingCounts>()
  for (const row of (itemRows ?? []) as { meeting_id: string }[]) {
    const existing = map.get(row.meeting_id)
    if (existing) {
      existing.agenda_item_count++
    } else {
      map.set(row.meeting_id, {
        meeting_id: row.meeting_id,
        agenda_item_count: 1,
        vote_count: 0,
        categories: [],
        topic_labels: [],
      })
    }
  }

  // Vote counts and categories/topics are not available in fallback mode —
  // item counts are the critical data. Votes show as 0 until RPC is restored.
  return map
}

/** Enrich a meetings array with counts from the shared fetchMeetingCounts helper.
 *  agenda_item_count comes from the stored column on meetings (trigger-maintained),
 *  NOT the RPC — eliminates ISR failures when the RPC times out. */
export function applyMeetingCounts(meetings: Meeting[], countMap: Map<string, MeetingCounts>) {
  return meetings.map((m) => {
    const c = countMap.get(m.id)
    const allCats = c?.categories ?? []
    const allLabels = c?.topic_labels ?? []
    return {
      ...m,
      // Stored column is authoritative; || falls through on 0 to RPC fallback
      agenda_item_count: Number(m.agenda_item_count || c?.agenda_item_count || 0),
      vote_count: Number(c?.vote_count ?? 0),
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
    .single()

  if (error || !meeting) return null

  // These reads depend only on the meeting, so start them together.
  const [
    { data: items },
    { data: attendance },
    { data: closedSession },
    { data: commentRows },
    allOfficials,
  ] = await Promise.all([
    supabase
      .from('agenda_items')
      .select('*')
      .is('agenda_source_retired_at', null)
      .eq('meeting_id', meetingId)
      .order('item_number'),
    supabase
      .from('meeting_attendance')
      .select('*, officials(name, role)')
      .eq('meeting_id', meetingId),
    supabase
      .from('closed_session_items')
      .select('*')
      .eq('meeting_id', meetingId),
    supabase
      .from('public_comments')
      .select('id, agenda_item_id, speaker_name, comment_type, method, source')
      .eq('meeting_id', meetingId),
    getOfficials(meeting.city_fips as string),
  ])

  // Fetch motions for all items
  const itemIds = (items ?? []).map((i) => i.id)
  const { data: motions } = itemIds.length > 0
    ? await supabase
        .from('motions')
        .select('*')
        .in('agenda_item_id', itemIds)
        .order('sequence_number')
    : { data: [] }

  // Fetch votes for all motions
  const motionIds = (motions ?? []).map((m) => m.id)
  const { data: votes } = motionIds.length > 0
    ? await supabase
        .from('votes')
        .select('*')
        .in('motion_id', motionIds)
    : { data: [] }

  // Build a lookup for notable speaker detection.
  const officialNameMap = new Map(
    allOfficials.map((o) => [o.name.toLowerCase(), o])
  )

  // Build per-item comment counts, summaries, and channel breakdowns
  const commentCountByItem = new Map<string, number>()
  const commentSpeakersByItem = new Map<string, string[]>()
  const spokenByItem = new Map<string, number>()
  const writtenByItem = new Map<string, number>()
  const commentSourceByItem = new Map<string, string | null>()
  let totalPublicComments = 0
  for (const c of (commentRows ?? [])) {
    if (c.agenda_item_id) {
      const itemId = c.agenda_item_id as string
      commentCountByItem.set(itemId, (commentCountByItem.get(itemId) ?? 0) + 1)
      const speakers = commentSpeakersByItem.get(itemId) ?? []
      if (c.speaker_name) speakers.push(c.speaker_name as string)
      commentSpeakersByItem.set(itemId, speakers)
      if ((c.comment_type as string) === 'written') {
        writtenByItem.set(itemId, (writtenByItem.get(itemId) ?? 0) + 1)
      } else {
        spokenByItem.set(itemId, (spokenByItem.get(itemId) ?? 0) + 1)
      }
      if (!commentSourceByItem.has(itemId)) {
        commentSourceByItem.set(itemId, (c.source as string | null) ?? null)
      }
    }
    totalPublicComments++
  }

  // Batch-fetch theme narratives for items with comments (inline community voice)
  const itemIdsWithComments = [...commentCountByItem.keys()]
  const themeNarrativesByItem = new Map<string, ThemeNarrative[]>()

  if (itemIdsWithComments.length > 0) {
    // Fetch theme narratives with theme metadata
    const { data: narrativeRows } = await supabase
      .from('item_theme_narratives')
      .select('agenda_item_id, narrative, comment_count, confidence, generated_at, comment_themes(id, slug, label, description)')
      .in('agenda_item_id', itemIdsWithComments)
      .order('comment_count', { ascending: false })

    // Fetch comment-to-theme assignments for per-theme channel counts
    const allCommentIds = (commentRows ?? [])
      .filter((c) => c.agenda_item_id && itemIdsWithComments.includes(c.agenda_item_id as string))
      .map((c) => c.id as string)

    const { data: assignmentRows } = allCommentIds.length > 0
      ? await supabase
          .from('comment_theme_assignments')
          .select('comment_id, comment_themes(slug)')
          .in('comment_id', allCommentIds)
      : { data: [] }

    // Build comment lookups by ID
    const commentTypeById = new Map<string, string>()
    const commentItemById = new Map<string, string>()
    const commentDetailById = new Map<string, { speaker_name: string; method: string; comment_type: string }>()
    for (const c of commentRows ?? []) {
      if (c.id) {
        const id = c.id as string
        commentTypeById.set(id, (c.comment_type as string) ?? 'public')
        if (c.agenda_item_id) commentItemById.set(id, c.agenda_item_id as string)
        commentDetailById.set(id, {
          speaker_name: (c.speaker_name as string) || 'Anonymous',
          method: (c.method as string) || 'unknown',
          comment_type: (c.comment_type as string) ?? 'public',
        })
      }
    }

    // Compute per-theme counts and comment lists per item
    // A comment can be assigned to multiple themes, so iterate assignments directly
    // Key: "itemId:themeSlug" → { spoken, written, comments }
    type ThemeAccum = { spoken: number; written: number; comments: { speaker_name: string; method: string; comment_type: string }[] }
    const themeChannelCounts = new Map<string, ThemeAccum>()
    for (const a of assignmentRows ?? []) {
      const theme = a.comment_themes as unknown as { slug: string } | null
      if (!theme?.slug) continue
      const commentId = a.comment_id as string
      const itemId = commentItemById.get(commentId)
      if (!itemId) continue
      const commentType = commentTypeById.get(commentId) ?? 'public'
      const detail = commentDetailById.get(commentId)
      const key = `${itemId}:${theme.slug}`
      const accum = themeChannelCounts.get(key) ?? { spoken: 0, written: 0, comments: [] }
      if (commentType === 'written') accum.written++
      else accum.spoken++
      if (detail) accum.comments.push(detail)
      themeChannelCounts.set(key, accum)
    }

    // Group narratives by item, attaching channel counts and comment lists
    for (const r of narrativeRows ?? []) {
      const itemId = r.agenda_item_id as string
      const theme = r.comment_themes as unknown as CommentTheme
      const slug = theme?.slug
      const channelKey = `${itemId}:${slug}`
      const accum = themeChannelCounts.get(channelKey) ?? { spoken: 0, written: 0, comments: [] }

      const narrative: ThemeNarrative = {
        theme,
        narrative: r.narrative as string,
        comment_count: r.comment_count as number,
        confidence: r.confidence as number,
        generated_at: r.generated_at as string,
        spoken_count: accum.spoken,
        written_count: accum.written,
        comments: accum.comments,
      }

      const arr = themeNarrativesByItem.get(itemId) ?? []
      arr.push(narrative)
      themeNarrativesByItem.set(itemId, arr)
    }
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

    // S20: only use YouTube-sourced count from agenda_items.public_comment_count
    // (set by youtube_comments.py). NULL = no data, don't fall back to
    // unreliable public_comments JOIN. Items without YouTube data show nothing.
    const safeCount = i.public_comment_count ?? 0

    return {
      ...i,
      motions: motionsByItem.get(i.id) ?? [],
      public_comment_count: safeCount,
      comment_summary: safeCount > 0 ? { total: safeCount, notable_speakers: notable } : undefined,
      theme_narratives: themeNarrativesByItem.get(i.id),
      spoken_comment_count: spokenByItem.get(i.id) ?? 0,
      written_comment_count: writtenByItem.get(i.id) ?? 0,
      comment_source: commentSourceByItem.get(i.id) ?? null,
    }
  })

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
    total_public_comments: totalPublicComments,
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

