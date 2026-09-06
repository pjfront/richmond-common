import type { SupabaseClient } from '@supabase/supabase-js'
import { isSubscriptionSubject, SUBSCRIPTION_SUBJECTS } from './subscription-subjects'
import { filterMeetingsForTopicPreferences } from './subscription-preferences'
import type { PublicBrief } from './queries/civic-briefs'

export interface DigestBrief extends PublicBrief { subject_key: string }
export interface DigestPreferenceRow { subscriber_id: string; preference_type: string; preference_value: string }
export const MAX_DIGEST_BRIEFS_PER_WEEK = 40
const BRIEF_COLUMNS = 'id,subject_key,title,body,sources,content_version,published_at'

export function digestBriefHref(brief: Pick<DigestBrief, 'id' | 'subject_key' | 'content_version' | 'published_at'>): string {
  const subject = SUBSCRIPTION_SUBJECTS.find(row => row.id === brief.subject_key)
  if (!subject) throw new Error('Unknown digest subject')
  return `https://richmondcommons.org/updates/${brief.id}?version=${brief.content_version}&published=${encodeURIComponent(brief.published_at)}#brief-${brief.id}-v${brief.content_version}`
}

export async function loadPublishedDigestBriefs(supabase: SupabaseClient, periods: { start: string; end: string; contentKey: string }[]) {
  const byPeriod = new Map<string, DigestBrief[]>()
  // Recovery shares one bounded scan across its already-persisted weeks.
  if (!periods.length) return byPeriod
  const exclusiveEnd = (end: string) => { const date = new Date(`${end}T00:00:00Z`); date.setUTCDate(date.getUTCDate() + 1); return date.toISOString() }
  const filter = periods.map(period => `and(published_at.gte.${period.start}T00:00:00.000Z,published_at.lt.${exclusiveEnd(period.end)})`).join(',')
  const { data, error } = await supabase.from('civic_brief_candidates').select(BRIEF_COLUMNS)
    .eq('status', 'published').in('subject_key', SUBSCRIPTION_SUBJECTS.map(subject => subject.id))
    .or(filter).order('published_at', { ascending: false }).order('id', { ascending: true }).limit(201)
  if (error) throw new Error('Published digest updates could not be loaded')
  if ((data ?? []).length > 200) throw new Error('Published digest source cap exceeded')
  const rows = (data ?? []) as unknown as DigestBrief[]
  for (const row of rows) {
    if (!isSubscriptionSubject(row.subject_key) || !Number.isSafeInteger(row.content_version) || row.content_version < 1
      || !row.published_at || !Number.isFinite(Date.parse(row.published_at)) || !row.title?.trim() || !row.body?.trim() || !Array.isArray(row.sources) || !row.sources.length
      || row.sources.some(source => {
        try { const url = new URL(source.url); return !['http:', 'https:'].includes(url.protocol) || Boolean(url.username || url.password) || ![1, 2].includes(source.source_tier) || !source.title?.trim() } catch { return true }
      })) throw new Error('Published digest update has incomplete review provenance')
  }
  for (const period of periods) {
    const selected = rows.filter(row => Date.parse(row.published_at) >= Date.parse(`${period.start}T00:00:00Z`) && Date.parse(row.published_at) < Date.parse(exclusiveEnd(period.end)))
    if (selected.length > MAX_DIGEST_BRIEFS_PER_WEEK) throw new Error('Published digest weekly cap exceeded')
    byPeriod.set(period.contentKey, selected)
  }
  return byPeriod
}

/** One consent contract used by initial weekly delivery and durable recovery. */
export function selectSubscriberDigest<T extends { id: string }>(
  meetings: T[], briefs: DigestBrief[], subscriber: { id: string; receive_council_updates?: boolean },
  preferences: DigestPreferenceRow[], meetingTopics: Map<string, Set<string>>, topicLabels: Map<string, string>,
) {
  const selected = preferences.filter(row => row.subscriber_id === subscriber.id)
  const topics = selected.filter(row => row.preference_type === 'topic').map(row => row.preference_value)
  const subjects = new Set(selected.filter(row => row.preference_type === 'subject' && isSubscriptionSubject(row.preference_value)).map(row => row.preference_value))
  return {
    meetings: subscriber.receive_council_updates === false ? [] : filterMeetingsForTopicPreferences(meetings, topics, meetingTopics, topicLabels),
    briefs: briefs.filter(brief => subjects.has(brief.subject_key)),
  }
}
