import { cache } from 'react'
import { unstable_cache } from 'next/cache'
import { readCompleteRecords } from '../complete-record-read'
import { supabase, RICHMOND_FIPS, COLS_TOPIC_COUNTS } from './_shared'

export interface TopicCount {
  topic_label: string
  item_count: number
  latest_meeting_date: string
}

interface TopicSourceRow {
  id: string
  topic_label: string
  meeting_id: string
  meetings: { meeting_date: string }
}

/** Persist only small aggregates, not the full source corpus; failed reads throw. */
const getTopicAggregates = cache(unstable_cache(async (cityFips: string) => {
  const rows = await readCompleteRecords('Topic records', (from, to) => supabase.from('agenda_items')
    .select(COLS_TOPIC_COUNTS, { count: 'exact' }).is('agenda_source_retired_at', null)
    .eq('meetings.city_fips', cityFips).not('topic_label', 'is', null)
    .order('id', { ascending: true }).range(from, to), { maxRows: 20_000, maxPages: 40 })
  const counts = new Map<string, { count: number; meetings: Set<string>; latest: string }>()
  for (const raw of rows) {
    const row = raw as unknown as TopicSourceRow
    if (!row.topic_label?.trim() || !row.meeting_id || !row.meetings?.meeting_date) throw new Error('Incomplete topic source record')
    const current = counts.get(row.topic_label) ?? { count: 0, meetings: new Set<string>(), latest: '' }
    current.count++
    current.meetings.add(row.meeting_id)
    if (row.meetings.meeting_date > current.latest) current.latest = row.meetings.meeting_date
    counts.set(row.topic_label, current)
  }
  return [...counts].map(([topic_label, group]) => ({ topic_label, item_count: group.count,
    meeting_count: group.meetings.size, latest_meeting_date: group.latest }))
}, ['complete-topic-aggregates-v1'], { revalidate: 3600, tags: ['agenda-items', 'topics'] }))

/** All topic counts from the same complete cohort used for promotion. */
export async function getTopicCounts(cityFips = RICHMOND_FIPS): Promise<TopicCount[]> {
  return (await getTopicAggregates(cityFips)).map(row => ({ topic_label: row.topic_label,
    item_count: row.item_count, latest_meeting_date: row.latest_meeting_date }))
    .sort((a, b) => b.item_count - a.item_count)
}

export interface TopicItem {
  id: string
  meeting_id: string
  meeting_date: string
  meeting_type: string
  item_number: string
  title: string
  summary_headline: string | null
  category: string | null
}

const COLS_TOPIC_ITEM = 'id, meeting_id, item_number, title, summary_headline, category, meetings!inner(meeting_date, meeting_type, city_fips)'

/** Get agenda items for a specific topic label, newest first. */
export async function getTopicItems(
  topicLabel: string,
  limit = 50,
  cityFips = RICHMOND_FIPS,
): Promise<TopicItem[]> {
  const { data, error } = await supabase
    .from('agenda_items')
    .select(COLS_TOPIC_ITEM)
    .is('agenda_source_retired_at', null)
    .eq('topic_label', topicLabel)
    .eq('meetings.city_fips', cityFips)
    .order('meetings(meeting_date)', { ascending: false })
    .order('id', { ascending: true })
    .limit(limit)

  if (error || !data) {
    throw new Error('Topic items are temporarily unavailable')
  }

  return (data as Array<Record<string, unknown>>).map((row) => {
    const meeting = row.meetings as unknown as { meeting_date: string; meeting_type: string }
    return {
      id: row.id as string,
      meeting_id: row.meeting_id as string,
      meeting_date: meeting.meeting_date,
      meeting_type: meeting.meeting_type,
      item_number: row.item_number as string,
      title: row.title as string,
      summary_headline: row.summary_headline as string | null,
      category: row.category as string | null,
    }
  })
}


// ─── Promoted topics (organic recurrence-based taxonomy) ────
// A topic_label only earns a navigation surface (sidebar chip,
// /topics card) once it has BOTH crossed an item-count bar AND
// appeared in multiple distinct meetings. The two-axis test rules
// out single-meeting clusters (6 closed-session items tagged the
// same way doesn't prove cross-meeting interest) while still
// promoting issues that genuinely recur. Both knobs are editorial.

export const TOPIC_PROMOTION_MIN_ITEMS = 5
export const TOPIC_PROMOTION_MIN_MEETINGS = 3

/** Back-compat alias used in user-facing copy on /topics. */
export const TOPIC_PROMOTION_THRESHOLD = TOPIC_PROMOTION_MIN_ITEMS

export interface PromotedTopic {
  label: string
  slug: string
  item_count: number
  meeting_count: number
  latest_meeting_date: string
}

/** Convert a topic_label into a URL-safe slug. */
export function topicLabelToSlug(label: string): string {
  return label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

/** Topics passing both item and meeting recurrence thresholds, sorted by recency. */
export async function getPromotedTopics(
  minItems = TOPIC_PROMOTION_MIN_ITEMS,
  minMeetings = TOPIC_PROMOTION_MIN_MEETINGS,
  cityFips = RICHMOND_FIPS,
): Promise<PromotedTopic[]> {
  return (await getTopicAggregates(cityFips))
    .filter(row => row.item_count >= minItems && row.meeting_count >= minMeetings)
    .map(row => ({ label: row.topic_label, slug: topicLabelToSlug(row.topic_label), item_count: row.item_count,
      meeting_count: row.meeting_count, latest_meeting_date: row.latest_meeting_date }))
    .sort((a, b) => b.latest_meeting_date.localeCompare(a.latest_meeting_date))
}

/** JSON-serializable label list for passing across server→client boundaries. */
export async function getPromotedTopicLabels(
  minItems = TOPIC_PROMOTION_MIN_ITEMS,
  minMeetings = TOPIC_PROMOTION_MIN_MEETINGS,
  cityFips = RICHMOND_FIPS,
): Promise<string[]> {
  const topics = await getPromotedTopics(minItems, minMeetings, cityFips)
  return topics.map((t) => t.label)
}

