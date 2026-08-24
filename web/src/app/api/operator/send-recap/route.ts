import { NextResponse, type NextRequest } from 'next/server'
import { getSupabaseAdmin } from '@/lib/supabase-admin'
import { sendEmail, buildRecapEmail, buildOrientationEmail } from '@/lib/email'
import {
  MAX_BROADCAST_RECIPIENTS,
  activationScopedContentKey,
  ensureBoundedRecipients,
  sendRecapBroadcast,
  type DeliverySubscriber,
} from '@/lib/email-delivery'
import {
  RECAP_SOURCE_COLUMNS,
  selectPersistedRecap,
  type PersistedRecapSource,
} from '@/lib/email-content-source'
import { withOperatorAuth } from '@/lib/operator-auth'
import { logEvent, requestContext } from '@/lib/logger'
import type { Provenance } from '@/lib/types'

const RICHMOND_FIPS = '0660620'
const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://richmondcommons.org'
const OPERATOR_EMAIL_MEETING_COLUMNS = `${RECAP_SOURCE_COLUMNS}, orientation_preview, orientation_preview_provenance, orientation_emailed_at, agenda_url`
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

interface OperatorEmailMeeting extends PersistedRecapSource {
  orientation_preview: string | null
  orientation_preview_provenance: Provenance | null
  orientation_emailed_at: string | null
  agenda_url: string | null
}

/**
 * GET /api/operator/send-recap?meeting_id=X
 * Returns recap preview HTML, subscriber count, and send status.
 */
export const GET = withOperatorAuth(async (request: NextRequest) => {
  const meetingId = request.nextUrl.searchParams.get('meeting_id')
  if (!meetingId) {
    return NextResponse.json({ error: 'meeting_id is required' }, { status: 400 })
  }
  if (!UUID_RE.test(meetingId)) {
    return NextResponse.json({ error: 'meeting_id must be a UUID' }, { status: 400 })
  }

  const supabase = getSupabaseAdmin()

  const [meetingResult, subscriberResult] = await Promise.all([
    supabase
      .from('meetings')
      .select(OPERATOR_EMAIL_MEETING_COLUMNS)
      .eq('id', meetingId)
      .single(),
    supabase
      .from('email_subscribers')
      .select('id, current_activation_id')
      .eq('status', 'active')
      .eq('city_fips', RICHMOND_FIPS)
      .order('id', { ascending: true })
      .limit(MAX_BROADCAST_RECIPIENTS + 1),
  ])

  if (meetingResult.error || !meetingResult.data) {
    return NextResponse.json({ error: 'Meeting not found' }, { status: 404 })
  }
  if (subscriberResult.error) {
    return NextResponse.json({ error: 'Subscriber status is unavailable' }, { status: 503 })
  }

  const meeting = meetingResult.data as unknown as OperatorEmailMeeting
  const recap = selectPersistedRecap(meeting)
  let subscribers: DeliverySubscriber[]
  try {
    subscribers = ensureBoundedRecipients(
      (subscriberResult.data ?? []) as DeliverySubscriber[],
    )
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Subscriber status is unavailable' },
      { status: 503 },
    )
  }
  const subscriberCount = subscribers.length
  const legacyEmailedAt = (meeting.recap_emailed_at
    ?? meeting.transcript_recap_emailed_at) as string | null
  const baseContentKey = `meeting:${meetingId}`
  const expectedKeys = new Map(subscribers.map((subscriber) => [
    subscriber.id,
    activationScopedContentKey('recap', baseContentKey, subscriber.current_activation_id),
  ]))
  let deliveryRows: Array<{ subscriber_id: string; status: string; content_key: string }> = []
  if (!legacyEmailedAt && subscribers.length > 0) {
    const deliveryResult = await supabase
      .from('email_deliveries')
      .select('subscriber_id, status, content_key')
      .eq('delivery_kind', 'recap')
      .in('content_key', [...new Set(expectedKeys.values())])
      .in('subscriber_id', subscribers.map((subscriber) => subscriber.id))
    if (deliveryResult.error) {
      return NextResponse.json({ error: 'Delivery status is unavailable' }, { status: 503 })
    }
    deliveryRows = (deliveryResult.data ?? []) as typeof deliveryRows
  }
  const currentDeliveryRows = deliveryRows.filter((row) =>
    row.content_key === expectedKeys.get(row.subscriber_id),
  )
  const deliveredCount = legacyEmailedAt
    ? subscriberCount
    : currentDeliveryRows.filter((row) => row.status === 'sent').length
  // Retryable failures remain pending; only terminal manual-review rows belong
  // in the operator panel's failed bucket.
  const failedCount = legacyEmailedAt
    ? 0
    : currentDeliveryRows.filter((row) => row.status === 'manual_review').length

  const recapText = recap?.meeting_recap ?? null
  const recapSource = recap
    ? (recap.source === 'transcript' ? 'transcript' : 'agenda')
    : null

  let recapHtml: string | null = null
  if (recap) {
    const { html } = buildRecapEmail(
      recap,
      `${BASE_URL}/api/subscribe?token=preview`,
      recapSource === 'transcript' ? 'transcript' : undefined,
    )
    recapHtml = html
  }

  return NextResponse.json({
    has_recap: !!recapText,
    recap_source: recapSource,
    recap_html: recapHtml,
    subscriber_count: subscriberCount,
    delivered_count: deliveredCount,
    failed_count: failedCount,
    pending_count: legacyEmailedAt
      ? 0
      : Math.max(0, subscriberCount - deliveredCount - failedCount),
    recap_emailed_at: legacyEmailedAt,
    legacy_already_sent: Boolean(legacyEmailedAt),
    has_orientation: !meeting.source_cancelled_at && !!meeting.orientation_preview,
    orientation_emailed_at: meeting.orientation_emailed_at,
  })
})

/**
 * POST /api/operator/send-recap
 * Body: { "meeting_id": "uuid" }
 * Sends recap email to all active subscribers and records timestamp.
 */
export const POST = withOperatorAuth(async (request: NextRequest) => {
  const ctx = requestContext(request)
  const body = await request.json().catch(() => ({})) as Record<string, unknown>
  const meetingId = typeof body.meeting_id === 'string' ? body.meeting_id.trim() : ''
  const testEmail = typeof body.test_email === 'string' ? body.test_email.trim() : ''

  if (!meetingId) {
    logEvent('operator.send_recap.bad_request', { ...ctx, severity: 'warn' })
    return NextResponse.json({ error: 'meeting_id is required' }, { status: 400 })
  }

  const supabase = getSupabaseAdmin()

  const { data: meeting, error: meetingError } = await supabase
    .from('meetings')
    .select(OPERATOR_EMAIL_MEETING_COLUMNS)
    .eq('id', meetingId)
    .single()

  if (meetingError || !meeting) {
    return NextResponse.json({ error: 'Meeting not found' }, { status: 404 })
  }
  const operatorMeeting = meeting as unknown as OperatorEmailMeeting
  const recap = selectPersistedRecap(operatorMeeting)

  // Test email: send to a single address without updating timestamps
  if (testEmail) {
    const dummyUnsub = `${BASE_URL}/api/subscribe?token=test-preview`
    if (recap) {
      const { subject, html, text } = buildRecapEmail(
        recap,
        dummyUnsub,
        recap.source === 'transcript' ? 'transcript' : undefined,
      )
      const result = await sendEmail({ to: testEmail, subject, html, text })
      if (!result.success) {
        return NextResponse.json({ error: result.error ?? 'Send failed' }, { status: 500 })
      }
      return NextResponse.json({ sent: 1, type: 'recap', test: true })
    }

    if (!operatorMeeting.source_cancelled_at && operatorMeeting.orientation_preview) {
      const { subject, html, text } = buildOrientationEmail(
        {
          id: operatorMeeting.id,
          meeting_date: operatorMeeting.meeting_date,
          orientation_preview: operatorMeeting.orientation_preview,
          orientation_preview_provenance: operatorMeeting.orientation_preview_provenance,
          agenda_url: operatorMeeting.agenda_url,
        },
        dummyUnsub,
      )
      const result = await sendEmail({ to: testEmail, subject, html, text })
      if (!result.success) {
        return NextResponse.json({ error: result.error ?? 'Send failed' }, { status: 500 })
      }
      return NextResponse.json({ sent: 1, type: 'orientation', test: true })
    }

    return NextResponse.json(
      { error: 'No recap or orientation preview available for this meeting.' },
      { status: 404 },
    )
  }

  if (!recap) {
    return NextResponse.json(
      { error: 'No recap available for this meeting.' },
      { status: 404 },
    )
  }

  const legacyEmailedAt = recap.recap_emailed_at
    ?? recap.transcript_recap_emailed_at
  if (legacyEmailedAt) {
    return NextResponse.json({
      sent: 0,
      already_sent: true,
      legacy_already_sent: true,
      emailed_at: legacyEmailedAt,
      reason: 'legacy recap delivery marker is already set',
    })
  }

  let result
  try {
    result = await sendRecapBroadcast(supabase, recap, RICHMOND_FIPS)
  } catch (deliveryError) {
    return NextResponse.json(
      { error: deliveryError instanceof Error ? deliveryError.message : 'Delivery failed' },
      { status: 503 },
    )
  }

  if (!result.fully_delivered) {
    logEvent('operator.send_recap.partial_failure', {
      ...ctx,
      severity: 'error',
      meeting_id: meetingId,
      sent: result.sent,
      failed: result.failed,
      deferred: result.deferred,
      manual_review: result.manual_review,
    })
  }

  logEvent('operator.send_recap.broadcast', {
    ...ctx,
    meeting_id: meetingId,
    ...result,
  })
  return NextResponse.json({ ...result }, { status: result.fully_delivered ? 200 : 503 })
})
