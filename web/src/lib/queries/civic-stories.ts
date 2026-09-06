import { unstable_cache } from 'next/cache'
import { cache } from 'react'
import { CIVIC_STORIES, matchesCivicStory, STORY_CONTEXT_VERSION } from '@/data/civic-stories'
import { agendaItemPath } from '@/lib/format'
import { RICHMOND_COUNCIL_BODY_TYPE } from '@/lib/orientation-scope'
import { COLS_RESIDENT_AGENDA_ITEM, COLS_RESIDENT_MEETING, RICHMOND_FIPS, supabase } from './_shared'

export const RECENT_COUNCIL_LIMIT = 16
export const UPCOMING_COUNCIL_LIMIT = 6
export const STORY_AGENDA_LIMIT = 1000

export interface ResidentMeeting {
  id: string
  meeting_date: string
  meeting_type: string
  agenda_url: string | null
  source_meeting_guid: string | null
}

export interface ResidentAgendaItem {
  id: string
  meeting_id: string
  item_number: string
  title: string
  topic_label: string | null
}

export interface StoryAgendaEntry extends ResidentAgendaItem {
  meeting_date: string
  agenda_url: string | null
  href: string
  upcoming: boolean
}

export interface ResidentSnapshot {
  status: 'available' | 'unavailable'
  fetchedAt: string | null
  upcoming: ResidentMeeting[]
  recent: ResidentMeeting[]
  entries: Record<string, StoryAgendaEntry[]>
  itemLimitReached: boolean
}

export function richmondDate(now = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Los_Angeles', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(now)
}

/** Deduplicate source aliases only, never merge distinct meetings merely by date. */
export function uniqueResidentMeetings(meetings: ResidentMeeting[]): ResidentMeeting[] {
  const seen = new Set<string>()
  return meetings.filter(meeting => {
    const key = meeting.source_meeting_guid || meeting.agenda_url || meeting.id
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

export function groupStoryAgendaEntries(items: ResidentAgendaItem[], meetings: ResidentMeeting[], today: string): Record<string, StoryAgendaEntry[]> {
  const meetingById = new Map(meetings.map(meeting => [meeting.id, meeting]))
  return Object.fromEntries(CIVIC_STORIES.map(story => {
    const seen = new Set<string>()
    const entries = items.flatMap(item => {
      const meeting = meetingById.get(item.meeting_id)
      if (!meeting || !matchesCivicStory(story, item.title, item.topic_label)) return []
      const key = `${meeting.source_meeting_guid || meeting.agenda_url || meeting.id}:${item.item_number.toLowerCase()}`
      if (seen.has(key)) return []
      seen.add(key)
      return [{ ...item, meeting_date: meeting.meeting_date, agenda_url: meeting.agenda_url, href: agendaItemPath(meeting.id, item.item_number), upcoming: meeting.meeting_date >= today }]
    }).sort((a, b) => b.meeting_date.localeCompare(a.meeting_date) || a.item_number.localeCompare(b.item_number, undefined, { numeric: true }))
    return [story.slug, entries]
  }))
}

// Errors escape the cached function. A failed refresh must not replace a good
// snapshot with an apparently successful empty result. No generation on reads.
const readResidentSnapshot = unstable_cache(async (today: string): Promise<ResidentSnapshot> => {
  const base = () => supabase.from('meetings').select(COLS_RESIDENT_MEETING)
    .eq('city_fips', RICHMOND_FIPS)
    .eq('bodies.body_type', RICHMOND_COUNCIL_BODY_TYPE)
    .is('source_cancelled_at', null)
  const [past, future] = await Promise.all([
    base().lt('meeting_date', today).order('meeting_date', { ascending: false }).limit(RECENT_COUNCIL_LIMIT),
    base().gte('meeting_date', today).order('meeting_date', { ascending: true }).limit(UPCOMING_COUNCIL_LIMIT),
  ])
  if (past.error || future.error) throw new Error('Council calendar lookup failed')
  const recent = uniqueResidentMeetings((past.data ?? []) as unknown as ResidentMeeting[])
  const upcoming = uniqueResidentMeetings((future.data ?? []) as unknown as ResidentMeeting[])
  const meetings = [...recent, ...upcoming]
  if (meetings.length === 0) throw new Error('Council calendar returned no source records')
  const { data, error } = await supabase.from('agenda_items').select(COLS_RESIDENT_AGENDA_ITEM)
    .in('meeting_id', meetings.map(meeting => meeting.id))
    .is('agenda_source_retired_at', null)
    .order('meeting_id').order('item_number').limit(STORY_AGENDA_LIMIT)
  if (error) throw new Error('Council agenda lookup failed')
  const items = (data ?? []) as unknown as ResidentAgendaItem[]
  return {
    status: 'available', fetchedAt: new Date().toISOString(), recent, upcoming,
    entries: groupStoryAgendaEntries(items, meetings, today),
    itemLimitReached: items.length === STORY_AGENDA_LIMIT,
  }
}, ['resident-story-snapshot', STORY_CONTEXT_VERSION], { revalidate: 3600, tags: ['meetings', 'agenda-items', 'civic-stories'] })

export const getResidentSnapshot = cache(async (): Promise<ResidentSnapshot> => {
  try {
    return await readResidentSnapshot(richmondDate())
  } catch (error) {
    console.error('[Richmond Commons] Resident agenda snapshot unavailable:', error instanceof Error ? error.message : 'unknown error')
    return { status: 'unavailable', fetchedAt: null, upcoming: [], recent: [], entries: {}, itemLimitReached: false }
  }
})
