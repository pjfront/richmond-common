import { NextRequest, NextResponse } from 'next/server'
import { getSupabaseAdmin } from '@/lib/supabase-admin'
import { buildDigestEmail, sendEmail } from '@/lib/email'
import {
  broadcastTrackedEmail,
  completedDigestWeek,
  loadActiveSubscribers,
  MAX_DIGEST_MEETINGS_PER_WEEK,
  MAX_DIGEST_PREFERENCE_ROWS,
  MAX_DIGEST_TOPIC_ROWS,
  type DeliverySubscriber,
} from '@/lib/email-delivery'
import {
  RECAP_SOURCE_COLUMNS,
  selectPersistedRecap,
  type PersistedRecapSource,
  type SelectedPersistedRecap,
} from '@/lib/email-content-source'
import { RICHMOND_LOCAL_ISSUES } from '@/lib/local-issues'
import { loadPublishedDigestBriefs, selectSubscriberDigest, type DigestPreferenceRow, type DigestBrief } from '@/lib/digest-selection'
import { PROVIDER_EMAIL_ID, readDigestCanaryProof } from '@/lib/digest-canary-proof'

const RICHMOND_FIPS = '0660620'
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://richmondcommons.org'
const DIGEST_CAPABILITY = 'subscriber-weekly-digest-v1'
// This release can send only the operator canary. The post-canary activation
// change must deliberately flip this code gate while adding the schedule.
const DIGEST_BROADCAST_ENABLED = false
const EMAIL_LOCAL_PATTERN = /^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+$/
const EMAIL_DOMAIN_PATTERN = /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$/

function configuredCanaryEmail(): string | null {
  const raw = process.env.SUBSCRIBER_CANARY_EMAIL ?? ''
  if (raw.length === 0 || raw.length > 254 || raw !== raw.trim()) {
    return null
  }
  const parts = raw.split('@')
  if (parts.length !== 2) return null
  const [local, domain] = parts
  if (
    local.length === 0
    || local.length > 64
    || local.startsWith('.')
    || local.endsWith('.')
    || local.includes('..')
    || !EMAIL_LOCAL_PATTERN.test(local)
    || !EMAIL_DOMAIN_PATTERN.test(domain)
  ) return null
  return raw
}

function isAuthorized(request: NextRequest): boolean {
  const secret = request.headers.get('authorization')?.replace('Bearer ', '')
  return Boolean(secret && secret === process.env.API_SECRET)
}

/** Read-only capability handshake, or redacted proof for the configured canary. */
export async function GET(request: NextRequest) {
  const headers = { 'Cache-Control': 'private, no-store' }
  if (!isAuthorized(request)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401, headers })
  }
  const params = request.nextUrl.searchParams
  if (params.size) {
    const ids = params.getAll('provider_id')
    const canaryEmail = configuredCanaryEmail()
    if (params.size !== 1 || ids.length !== 1 || !PROVIDER_EMAIL_ID.test(ids[0]) || !canaryEmail) {
      return NextResponse.json({ error: 'Canary provider proof unavailable' }, { status: 503, headers })
    }
    const proof = await readDigestCanaryProof(ids[0], canaryEmail)
    return proof
      ? NextResponse.json(proof, { headers })
      : NextResponse.json({ error: 'Canary provider proof unavailable' }, { status: 503, headers })
  }
  return NextResponse.json({
    capability: DIGEST_CAPABILITY,
    canary_ready: configuredCanaryEmail() !== null,
    broadcast_ready: DIGEST_BROADCAST_ENABLED,
  }, { headers })
}

/** Send the immediately completed calendar week's digest. */
export async function POST(request: NextRequest) {
  if (!isAuthorized(request)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const body = await request.json().catch(() => ({})) as Record<string, unknown>
  const mode = body.mode
  if (mode !== 'broadcast' && mode !== 'canary') {
    return NextResponse.json(
      { error: 'An explicit mode of broadcast or canary is required' },
      { status: 400 },
    )
  }
  if (mode === 'broadcast' && !DIGEST_BROADCAST_ENABLED) {
    return NextResponse.json(
      { error: 'Subscriber digest broadcast is not activated' },
      { status: 409 },
    )
  }
  const canaryEmail = mode === 'canary' ? configuredCanaryEmail() : null
  if (mode === 'canary' && canaryEmail === null) {
    return NextResponse.json(
      { error: 'SUBSCRIBER_CANARY_EMAIL is missing or invalid' },
      { status: 503 },
    )
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
    .limit(MAX_DIGEST_MEETINGS_PER_WEEK + 1)

  if (meetingError) {
    return NextResponse.json({ error: 'Failed to fetch meetings' }, { status: 500 })
  }
  if ((meetingRows ?? []).length > MAX_DIGEST_MEETINGS_PER_WEEK) {
    return NextResponse.json(
      { error: `Digest meeting cap exceeded (${MAX_DIGEST_MEETINGS_PER_WEEK})` },
      { status: 503 },
    )
  }
  const meetings = (meetingRows ?? [])
    .map((meeting) => selectPersistedRecap(meeting as unknown as PersistedRecapSource))
    .filter((meeting): meeting is SelectedPersistedRecap => Boolean(meeting))
  try {
    const briefs = (await loadPublishedDigestBriefs(supabase, [period])).get(period.contentKey) ?? []
    if (meetings.length === 0 && briefs.length === 0) {
      return NextResponse.json({ mode, sent: 0, period, reason: 'no recaps or reviewed updates in completed week' })
    }
    if (mode === 'canary') {
      if (canaryEmail === null) {
        throw new Error('Canary recipient validation invariant failed')
      }
      const content = buildDigestEmail(
        meetings,
        `${SITE_URL}/subscribe`,
        undefined,
        { canary: true, briefs },
      )
      const result = await sendEmail({
        to: canaryEmail,
        ...content,
        idempotencyKey: `rc:digest:canary:${period.contentKey}`,
      })
      // Preserve the exact accepted message identity for read-only provider
      // verification. A successful transport without an ID is ambiguous and
      // must never authorize activation or another send.
      const providerConfirmed = result.success && typeof result.providerId === 'string'
        && PROVIDER_EMAIL_ID.test(result.providerId)
      return NextResponse.json({
        mode,
        period,
        meeting_count: meetings.length,
        reviewed_update_count: briefs.length,
        sent: providerConfirmed ? 1 : 0,
        provider_confirmed: providerConfirmed,
        provider_id: providerConfirmed ? result.providerId : undefined,
        ambiguous: result.ambiguous === true || (result.success && !providerConfirmed),
        error: providerConfirmed ? undefined : result.success
          ? 'Email provider acceptance could not be tied to a valid message ID'
          : result.error,
      }, { status: providerConfirmed ? 200 : 503 })
    }

    const subscribers = await loadActiveSubscribers(supabase, RICHMOND_FIPS)
    if (subscribers.length === 0) {
      return NextResponse.json({ sent: 0, period, reason: 'no active subscribers' })
    }

    const subscriberIds = subscribers.map((subscriber) => subscriber.id)
    const meetingIds = meetings.map((meeting) => meeting.id)
    const [preferencesResult, topicsResult] = await Promise.all([
      supabase
        .from('email_preferences')
        .select('subscriber_id, preference_type, preference_value')
        .in('preference_type', ['topic', 'subject'])
        .in('subscriber_id', subscriberIds)
        .limit(MAX_DIGEST_PREFERENCE_ROWS + 1),
      supabase
        .from('agenda_items')
        .select('meeting_id, topic_label')
        .in('meeting_id', meetingIds)
        .is('agenda_source_retired_at', null)
        .not('topic_label', 'is', null)
        .limit(MAX_DIGEST_TOPIC_ROWS + 1),
    ])

    if (preferencesResult.error || topicsResult.error) {
      return NextResponse.json({ error: 'Failed to load digest preferences' }, { status: 500 })
    }
    if ((preferencesResult.data ?? []).length > MAX_DIGEST_PREFERENCE_ROWS) {
      return NextResponse.json(
        { error: `Digest preference cap exceeded (${MAX_DIGEST_PREFERENCE_ROWS})` },
        { status: 503 },
      )
    }
    if ((topicsResult.data ?? []).length > MAX_DIGEST_TOPIC_ROWS) {
      return NextResponse.json(
        { error: `Digest topic cap exceeded (${MAX_DIGEST_TOPIC_ROWS})` },
        { status: 503 },
      )
    }

    const preferences = (preferencesResult.data ?? []) as DigestPreferenceRow[]

    const topicsByMeeting = new Map<string, Set<string>>()
    for (const row of topicsResult.data ?? []) {
      const labels = topicsByMeeting.get(row.meeting_id as string) ?? new Set<string>()
      labels.add(row.topic_label as string)
      topicsByMeeting.set(row.meeting_id as string, labels)
    }
    const labelsById = new Map(RICHMOND_LOCAL_ISSUES.map((issue) => [issue.id, issue.label]))

    const eligibleSubscribers: DeliverySubscriber[] = []
    const digestBySubscriber = new Map<string, { meetings: SelectedPersistedRecap[]; briefs: DigestBrief[] }>()
    for (const subscriber of subscribers) {
      const selected = selectSubscriberDigest(meetings, briefs, subscriber, preferences, topicsByMeeting, labelsById)
      if (selected.meetings.length > 0 || selected.briefs.length > 0) {
        eligibleSubscribers.push(subscriber)
        digestBySubscriber.set(subscriber.id, selected)
      }
    }

    const result = await broadcastTrackedEmail({
      supabase,
      subscribers: eligibleSubscribers,
      kind: 'digest',
      contentKey: period.contentKey,
      build: (subscriber, { unsubscribeUrl, manageUrl }) => buildDigestEmail(
        digestBySubscriber.get(subscriber.id)?.meetings ?? [],
        unsubscribeUrl,
        manageUrl,
        { briefs: digestBySubscriber.get(subscriber.id)?.briefs ?? [] },
      ),
      briefVersions: subscriber => (digestBySubscriber.get(subscriber.id)?.briefs ?? [])
        .map(({ id, content_version, published_at }) => ({ id, content_version, published_at })),
      containsCouncilContent: subscriber => Boolean(digestBySubscriber.get(subscriber.id)?.meetings.length),
    })

    return NextResponse.json({
      period,
      meeting_count: meetings.length,
      reviewed_update_count: briefs.length,
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
