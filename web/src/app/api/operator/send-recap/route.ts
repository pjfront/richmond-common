import { NextResponse, type NextRequest } from 'next/server'
import { getSupabaseAdmin } from '@/lib/supabase-admin'
import { sendEmail, buildRecapEmail, buildOrientationEmail } from '@/lib/email'
import { sendRecapBroadcast } from '@/lib/email-delivery'
import { withOperatorAuth } from '@/lib/operator-auth'
import { logEvent, requestContext } from '@/lib/logger'
import type { Provenance } from '@/lib/types'

const RICHMOND_FIPS = '0660620'
const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://richmondcommons.org'

/**
 * GET /api/operator/send-recap?meeting_id=X
 * Returns recap preview HTML, subscriber count, and send status.
 */
export const GET = withOperatorAuth(async (request: NextRequest) => {
  const meetingId = request.nextUrl.searchParams.get('meeting_id')
  if (!meetingId) {
    return NextResponse.json({ error: 'meeting_id is required' }, { status: 400 })
  }

  const supabase = getSupabaseAdmin()

  const [meetingResult, subscriberResult] = await Promise.all([
    supabase
      .from('meetings')
      .select('id, meeting_date, meeting_type, meeting_recap, meeting_recap_provenance, transcript_recap, transcript_recap_provenance, minutes_url, recap_emailed_at, transcript_recap_emailed_at, orientation_preview, orientation_preview_provenance, orientation_emailed_at')
      .eq('id', meetingId)
      .single(),
    supabase
      .from('email_subscribers')
      .select('id', { count: 'exact', head: true })
      .eq('status', 'active')
      .eq('city_fips', RICHMOND_FIPS),
  ])

  if (meetingResult.error || !meetingResult.data) {
    return NextResponse.json({ error: 'Meeting not found' }, { status: 404 })
  }

  const meeting = meetingResult.data
  const subscriberCount = subscriberResult.count ?? 0
  const legacyEmailedAt = (meeting.recap_emailed_at
    ?? meeting.transcript_recap_emailed_at) as string | null
  const { data: deliveryRows } = await supabase
    .from('email_deliveries')
    .select('status')
    .eq('delivery_kind', 'recap')
    .eq('content_key', `meeting:${meetingId}`)
  const deliveredCount = legacyEmailedAt
    ? subscriberCount
    : (deliveryRows ?? []).filter((row) => row.status === 'sent').length
  // Retryable failures remain pending; only terminal manual-review rows belong
  // in the operator panel's failed bucket.
  const failedCount = legacyEmailedAt
    ? 0
    : (deliveryRows ?? []).filter((row) => row.status === 'manual_review').length

  const recapText = (meeting.meeting_recap ?? meeting.transcript_recap) as string | null
  const recapSource = meeting.meeting_recap ? 'agenda' : (meeting.transcript_recap ? 'transcript' : null)
  // Pick the matching provenance — meeting_recap and transcript_recap
  // each have their own column, so the "which artifact are we sending"
  // and "what is its provenance" decisions are colocated.
  const recapProvenance = meeting.meeting_recap
    ? meeting.meeting_recap_provenance
    : meeting.transcript_recap_provenance

  let recapHtml: string | null = null
  if (recapText) {
    const { html } = buildRecapEmail(
      {
        id: meeting.id as string,
        meeting_date: meeting.meeting_date as string,
        meeting_type: meeting.meeting_type as string,
        meeting_recap: recapText,
        minutes_url: meeting.minutes_url as string | null,
        meeting_recap_provenance: recapProvenance ?? null,
      },
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
    has_orientation: !!meeting.orientation_preview,
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
    .select('id, meeting_date, meeting_type, meeting_recap, meeting_recap_provenance, transcript_recap, transcript_recap_provenance, minutes_url, recap_emailed_at, transcript_recap_emailed_at, orientation_preview, orientation_preview_provenance, agenda_url')
    .eq('id', meetingId)
    .single()

  if (meetingError || !meeting) {
    return NextResponse.json({ error: 'Meeting not found' }, { status: 404 })
  }

  // Test email: send to a single address without updating timestamps
  if (testEmail) {
    const dummyUnsub = `${BASE_URL}/api/subscribe?token=test-preview`
    const testRecapText = (meeting.meeting_recap ?? meeting.transcript_recap) as string | null
    const testRecapSource = meeting.meeting_recap ? 'agenda' : 'transcript'
    const testRecapProvenance = meeting.meeting_recap
      ? meeting.meeting_recap_provenance
      : meeting.transcript_recap_provenance

    if (testRecapText) {
      const { subject, html, text } = buildRecapEmail(
        {
          id: meeting.id as string,
          meeting_date: meeting.meeting_date as string,
          meeting_type: meeting.meeting_type as string,
          meeting_recap: testRecapText,
          minutes_url: meeting.minutes_url as string | null,
          meeting_recap_provenance: testRecapProvenance ?? null,
        },
        dummyUnsub,
        testRecapSource === 'transcript' ? 'transcript' : undefined,
      )
      const result = await sendEmail({ to: testEmail, subject, html, text })
      if (!result.success) {
        return NextResponse.json({ error: result.error ?? 'Send failed' }, { status: 500 })
      }
      return NextResponse.json({ sent: 1, type: 'recap', test: true })
    }

    if (meeting.orientation_preview) {
      const { subject, html, text } = buildOrientationEmail(
        {
          id: meeting.id as string,
          meeting_date: meeting.meeting_date as string,
          orientation_preview: meeting.orientation_preview as string,
          agenda_url: meeting.agenda_url as string | null,
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

  const broadcastRecapText = (meeting.meeting_recap ?? meeting.transcript_recap) as string | null
  const broadcastRecapSource = meeting.meeting_recap ? 'agenda' : 'transcript'
  const broadcastRecapProvenance = meeting.meeting_recap
    ? meeting.meeting_recap_provenance
    : meeting.transcript_recap_provenance

  if (!broadcastRecapText) {
    return NextResponse.json(
      { error: 'No recap available for this meeting.' },
      { status: 404 },
    )
  }

  const legacyEmailedAt = (meeting.recap_emailed_at
    ?? meeting.transcript_recap_emailed_at) as string | null
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
    result = await sendRecapBroadcast(supabase, {
      id: meeting.id as string,
      meeting_date: meeting.meeting_date as string,
      meeting_type: meeting.meeting_type as string,
      meeting_recap: broadcastRecapText,
      minutes_url: meeting.minutes_url as string | null,
      meeting_recap_provenance: (broadcastRecapProvenance ?? null) as Provenance | null,
      source: broadcastRecapSource === 'transcript' ? 'transcript' : 'minutes',
      recap_emailed_at: null,
      transcript_recap_emailed_at: null,
    }, RICHMOND_FIPS)
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
