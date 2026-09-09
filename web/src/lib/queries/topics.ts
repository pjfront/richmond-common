import { supabase, RICHMOND_FIPS } from './_shared'
import { getAgendaMetadata } from './agenda-metadata'

export interface TopicCount {
  topic_label: string
  item_count: number
  latest_meeting_date: string
}

/** All topic counts from the same complete cohort used for promotion. */
export async function getTopicCounts(cityFips = RICHMOND_FIPS): Promise<TopicCount[]> {
  return (await getAgendaMetadata(cityFips)).topics.map(row => ({ topic_label: row.topic_label,
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
  return (await getAgendaMetadata(cityFips)).topics
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

