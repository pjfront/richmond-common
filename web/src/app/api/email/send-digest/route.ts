import { NextRequest, NextResponse } from 'next/server'
import { getSupabaseAdmin } from '@/lib/supabase-admin'
import { buildDigestEmail } from '@/lib/email'
import {
  broadcastTrackedEmail,
  completedDigestWeek,
  filterMeetingsForTopicPreferences,
  loadActiveSubscribers,
  type DeliverySubscriber,
} from '@/lib/email-delivery'
import {
  RECAP_SOURCE_COLUMNS,
  selectPersistedRecap,
  type PersistedRecapSource,
  type SelectedPersistedRecap,
} from '@/lib/email-content-source'
import { RICHMOND_LOCAL_ISSUES } from '@/lib/local-issues'

const RICHMOND_FIPS = '0660620'
/** Send the immediately completed calendar week's digest. */
export async function POST(request: NextRequest) {
  const secret = request.headers.get('authorization')?.replace('Bearer ', '')
  if (!secret || secret !== process.env.API_SECRET) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const supabase = getSupabaseAdmin()
  const period = completedDigestWeek()
  const { data: meetingRows, error: meetingError } = await supabase
    .from('meetings')
    .select(RECAP_SOURCE_COLUMNS)
    .eq('city_fips', RICHMOND_FIPS)
    .gte('meeting_date', period.start)
    .lte('meeting_date', period.end)
    .order('meeting_date', { ascending: false })
    .order('id', { ascending: true })

  if (meetingError) {
    return NextResponse.json({ error: 'Failed to fetch meetings' }, { status: 500 })
  }
  const meetings = (meetingRows ?? [])
    .map((meeting) => selectPersistedRecap(meeting as unknown as PersistedRecapSource))
    .filter((meeting): meeting is SelectedPersistedRecap => Boolean(meeting))
  if (meetings.length === 0) {
    return NextResponse.json({ sent: 0, period, reason: 'no recaps in completed week' })
  }

  try {
    const subscribers = await loadActiveSubscribers(supabase, RICHMOND_FIPS)
    if (subscribers.length === 0) {
      return NextResponse.json({ sent: 0, period, reason: 'no active subscribers' })
    }

    const subscriberIds = subscribers.map((subscriber) => subscriber.id)
    const meetingIds = meetings.map((meeting) => meeting.id)
    const [preferencesResult, topicsResult] = await Promise.all([
      supabase
        .from('email_preferences')
        .select('subscriber_id, preference_value')
        .eq('preference_type', 'topic')
        .in('subscriber_id', subscriberIds),
      supabase
        .from('agenda_items')
        .select('meeting_id, topic_label')
        .in('meeting_id', meetingIds)
        .is('agenda_source_retired_at', null)
        .not('topic_label', 'is', null),
    ])

    if (preferencesResult.error || topicsResult.error) {
      return NextResponse.json({ error: 'Failed to load digest preferences' }, { status: 500 })
    }

    const preferencesBySubscriber = new Map<string, string[]>()
    for (const row of preferencesResult.data ?? []) {
      const values = preferencesBySubscriber.get(row.subscriber_id as string) ?? []
      values.push(row.preference_value as string)
      preferencesBySubscriber.set(row.subscriber_id as string, values)
    }

    const topicsByMeeting = new Map<string, Set<string>>()
    for (const row of topicsResult.data ?? []) {
      const labels = topicsByMeeting.get(row.meeting_id as string) ?? new Set<string>()
      labels.add(row.topic_label as string)
      topicsByMeeting.set(row.meeting_id as string, labels)
    }
    const labelsById = new Map(RICHMOND_LOCAL_ISSUES.map((issue) => [issue.id, issue.label]))

    const eligibleSubscribers: DeliverySubscriber[] = []
    const digestBySubscriber = new Map<string, SelectedPersistedRecap[]>()
    for (const subscriber of subscribers) {
      const selectedMeetings = filterMeetingsForTopicPreferences(
        meetings,
        preferencesBySubscriber.get(subscriber.id) ?? [],
        topicsByMeeting,
        labelsById,
      )
      if (selectedMeetings.length > 0) {
        eligibleSubscribers.push(subscriber)
        digestBySubscriber.set(subscriber.id, selectedMeetings)
      }
    }

    const result = await broadcastTrackedEmail({
      supabase,
      subscribers: eligibleSubscribers,
      kind: 'digest',
      contentKey: period.contentKey,
      build: (subscriber, { unsubscribeUrl, manageUrl }) => buildDigestEmail(
        digestBySubscriber.get(subscriber.id) ?? [],
        unsubscribeUrl,
        manageUrl,
      ),
    })

    return NextResponse.json({
      period,
      meeting_count: meetings.length,
      preference_filtered_out: subscribers.length - eligibleSubscribers.length,
      ...result,
    }, { status: result.fully_delivered ? 200 : 503 })
  } catch (deliveryError) {
    return NextResponse.json(
      { error: deliveryError instanceof Error ? deliveryError.message : 'Delivery failed' },
      { status: 503 },
    )
  }
}
