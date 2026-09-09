import { cache } from 'react'
import { unstable_cache } from 'next/cache'
import { readCompleteRecords } from '../complete-record-read'
import { failReadPath } from '../read-path-unavailable'
import { AGENDA_METADATA_CACHE_SECONDS, AGENDA_METADATA_CACHE_TAG } from '../read-path-cache'
import { supabase, COLS_AGENDA_METADATA, COLS_MEETING_METADATA } from './_shared'
import type { MeetingWithCounts } from '../types'

type CompactMeeting = Omit<MeetingWithCounts, 'top_categories' | 'top_topic_labels'>
type MeetingSource = Omit<CompactMeeting, 'agenda_item_count' | 'all_categories' | 'all_topic_labels'> & {
  source_cancelled_at: string | null
}
interface AgendaSource {
  id: string
  meeting_id: string
  category: string | null
  topic_label: string | null
  agenda_source_retired_at: string | null
  meetings: { meeting_date: string; city_fips: string; source_cancelled_at: string | null }
}
export interface AgendaTopicAggregate {
  topic_label: string
  item_count: number
  meeting_count: number
  latest_meeting_date: string
}
interface AgendaMetadataSnapshot {
  meetings: CompactMeeting[]
  topics: AgendaTopicAggregate[]
}

const validText = (value: unknown): value is string => typeof value === 'string' && value.trim().length > 0
const nullableText = (value: unknown): value is string | null => value === null || validText(value)
const validDate = (value: unknown): value is string => typeof value === 'string'
  && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value))

/** One complete inventory establishes which meetings really have zero entries.
 * Counts, categories and topic recurrence all derive from the same active agenda
 * cohort. A failed, truncated or changed read never supplies partial aggregates.
 * These paginated HTTP reads are not a database transaction: parent mismatches
 * fail instead of guessing across a concurrent source change.
 */
async function readAgendaMetadata(cityFips: string): Promise<AgendaMetadataSnapshot> {
  const meetingRows = await readCompleteRecords('Meeting metadata', (from, to) => supabase.from('meetings')
    .select(COLS_MEETING_METADATA, { count: 'exact' }).eq('city_fips', cityFips)
    .is('source_cancelled_at', null).order('id').range(from, to))
  const meetings = new Map<string, { row: CompactMeeting; categories: Map<string, number>; labels: Map<string, number> }>()
  for (const raw of meetingRows) {
    const row = raw as unknown as MeetingSource
    if (!validText(row.id) || row.city_fips !== cityFips || !nullableText(row.body_id)
      || !validDate(row.meeting_date) || !validText(row.meeting_type) || !validText(row.created_at)
      || !nullableText(row.presiding_officer) || !nullableText(row.agenda_url) || !nullableText(row.minutes_url)
      || row.source_cancelled_at !== null) failReadPath('Meeting metadata', 'Invalid active meeting identity')
    // Pick source fields explicitly; never retain stored counts, summaries or source payloads.
    meetings.set(row.id, { row: { id: row.id, city_fips: row.city_fips, body_id: row.body_id,
      meeting_date: row.meeting_date, meeting_type: row.meeting_type, presiding_officer: row.presiding_officer,
      agenda_url: row.agenda_url, minutes_url: row.minutes_url, created_at: row.created_at,
      agenda_item_count: 0, all_categories: [], all_topic_labels: [] }, categories: new Map(), labels: new Map() })
  }
  const agenda = await readCompleteRecords('Agenda metadata', (from, to) => supabase.from('agenda_items')
    .select(COLS_AGENDA_METADATA, { count: 'exact' }).is('agenda_source_retired_at', null)
    .eq('meetings.city_fips', cityFips).is('meetings.source_cancelled_at', null)
    .order('id').range(from, to), { maxRows: 20_000, maxPages: 40 })
  const topics = new Map<string, { count: number; meetings: Set<string>; latest: string }>()
  for (const raw of agenda) {
    const row = raw as unknown as AgendaSource
    const parent = meetings.get(row.meeting_id)
    if (!validText(row.id) || !parent || row.agenda_source_retired_at !== null
      || !row.meetings || row.meetings.city_fips !== cityFips || row.meetings.source_cancelled_at !== null
      || row.meetings.meeting_date !== parent.row.meeting_date
      || !nullableText(row.category) || !nullableText(row.topic_label)) {
      failReadPath('Agenda metadata', 'Missing, changed or invalid active agenda parent')
    }
    parent.row.agenda_item_count++
    if (row.category !== null) parent.categories.set(row.category, (parent.categories.get(row.category) ?? 0) + 1)
    if (row.topic_label !== null) {
      // Preserve the existing meeting-card filter; global topic recurrence uses
      // all labelled entries, including procedural and uncategorized entries.
      if (row.category !== null && row.category !== 'procedural') {
        parent.labels.set(row.topic_label, (parent.labels.get(row.topic_label) ?? 0) + 1)
      }
      const topic = topics.get(row.topic_label) ?? { count: 0, meetings: new Set<string>(), latest: '' }
      topic.count++
      topic.meetings.add(row.meeting_id)
      if (parent.row.meeting_date > topic.latest) topic.latest = parent.row.meeting_date
      topics.set(row.topic_label, topic)
    }
  }
  const snapshot: AgendaMetadataSnapshot = {
    meetings: [...meetings.values()].map(({ row, categories, labels }) => ({ ...row,
      all_categories: [...categories].map(([category, count]) => ({ category, count }))
        .sort((a, b) => b.count - a.count || a.category.localeCompare(b.category)),
      all_topic_labels: [...labels].map(([label, count]) => ({ label, count }))
        .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label)),
    })).sort((a, b) => b.meeting_date.localeCompare(a.meeting_date) || a.id.localeCompare(b.id)),
    topics: [...topics].map(([topic_label, group]) => ({ topic_label, item_count: group.count,
      meeting_count: group.meetings.size, latest_meeting_date: group.latest })),
  }
  // Full source metadata is ~3 MB today. Cache only compact results, without
  // duplicate top-N arrays. Keep headroom below Next 16.1.6's 2 MiB cache limit.
  if (new TextEncoder().encode(JSON.stringify(snapshot)).byteLength >= 1_800_000) {
    failReadPath('Agenda metadata', 'Compact snapshot exceeded its cache size budget')
  }
  return snapshot
}

export const getAgendaMetadata = cache(unstable_cache(readAgendaMetadata,
  ['complete-active-agenda-metadata-v1'],
  { revalidate: AGENDA_METADATA_CACHE_SECONDS, tags: [AGENDA_METADATA_CACHE_TAG] }))

/** Add small card previews after the persistent cache boundary. */
export function meetingCards(snapshot: Awaited<ReturnType<typeof getAgendaMetadata>>): MeetingWithCounts[] {
  return snapshot.meetings.map(row => ({ ...row,
    top_categories: row.all_categories.slice(0, 4), top_topic_labels: row.all_topic_labels.slice(0, 5) }))
}
