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
import { RICHMOND_LOCAL_ISSUES } from '@/lib/local-issues'
import type { Provenance } from '@/lib/types'

const RICHMOND_FIPS = '0660620'

interface DigestMeeting {
  id: string
  meeting_date: string
  meeting_type: string
  meeting_recap: string
  minutes_url: string | null
  meeting_recap_provenance: Provenance | null
}
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
    .select('id, meeting_date, meeting_type, meeting_recap, meeting_recap_provenance, minutes_url')
    .eq('city_fips', RICHMOND_FIPS)
    .not('meeting_recap', 'is', null)
    .gte('meeting_date', period.start)
    .lte('meeting_date', period.end)
    .order('meeting_date', { ascending: false })

  if (meetingError) {
    return NextResponse.json({ error: 'Failed to fetch meetings' }, { status: 500 })
  }
  if (!meetingRows || meetingRows.length === 0) {
    return NextResponse.json({ sent: 0, period, reason: 'no recaps in completed week' })
  }

  const meetings: DigestMeeting[] = meetingRows.map((meeting) => ({
    id: meeting.id as string,
    meeting_date: meeting.meeting_date as string,
    meeting_type: meeting.meeting_type as string,
    meeting_recap: meeting.meeting_recap as string,
    minutes_url: meeting.minutes_url as string | null,
    meeting_recap_provenance: (meeting.meeting_recap_provenance ?? null) as Provenance | null,
  }))

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
    const digestBySubscriber = new Map<string, DigestMeeting[]>()
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
