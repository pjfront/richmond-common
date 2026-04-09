import { NextRequest, NextResponse } from 'next/server'
import { getSupabaseAdmin } from '@/lib/supabase-admin'
import { sendEmail, buildRecapEmail, buildOrientationEmail } from '@/lib/email'

const RICHMOND_FIPS = '0660620'
const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://richmondcommons.org'

function isOperator(request: NextRequest): boolean {
  return request.cookies.get('rtp_operator')?.value === 'active'
}

/**
 * GET /api/operator/send-recap?meeting_id=X
 * Returns recap preview HTML, subscriber count, and send status.
 */
export async function GET(request: NextRequest) {
  if (!isOperator(request)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const meetingId = request.nextUrl.searchParams.get('meeting_id')
  if (!meetingId) {
    return NextResponse.json({ error: 'meeting_id is required' }, { status: 400 })
  }

  const supabase = getSupabaseAdmin()

  const [meetingResult, subscriberResult] = await Promise.all([
    supabase
      .from('meetings')
      .select('id, meeting_date, meeting_type, meeting_recap, transcript_recap, minutes_url, recap_emailed_at, transcript_recap_emailed_at')
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

  const recapText = (meeting.meeting_recap ?? meeting.transcript_recap) as string | null
  const recapSource = meeting.meeting_recap ? 'agenda' : (meeting.transcript_recap ? 'transcript' : null)

  let recapHtml: string | null = null
  if (recapText) {
    const { html } = buildRecapEmail(
      {
        id: meeting.id as string,
        meeting_date: meeting.meeting_date as string,
        meeting_type: meeting.meeting_type as string,
        meeting_recap: recapText,
        minutes_url: meeting.minutes_url as string | null,
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
    recap_emailed_at: meeting.recap_emailed_at,
  })
}

/**
 * POST /api/operator/send-recap
 * Body: { "meeting_id": "uuid" }
 * Sends recap email to all active subscribers and records timestamp.
 */
export async function POST(request: NextRequest) {
  if (!isOperator(request)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const body = await request.json().catch(() => ({})) as Record<string, unknown>
  const meetingId = typeof body.meeting_id === 'string' ? body.meeting_id.trim() : ''
  const testEmail = typeof body.test_email === 'string' ? body.test_email.trim() : ''

  if (!meetingId) {
    return NextResponse.json({ error: 'meeting_id is required' }, { status: 400 })
  }

  const supabase = getSupabaseAdmin()

  const { data: meeting, error: meetingError } = await supabase
    .from('meetings')
    .select('id, meeting_date, meeting_type, meeting_recap, transcript_recap, minutes_url, orientation_preview, agenda_url')
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

    if (testRecapText) {
      const { subject, html, text } = buildRecapEmail(
        {
          id: meeting.id as string,
          meeting_date: meeting.meeting_date as string,
          meeting_type: meeting.meeting_type as string,
          meeting_recap: testRecapText,
          minutes_url: meeting.minutes_url as string | null,
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

  if (!broadcastRecapText) {
    return NextResponse.json(
      { error: 'No recap available for this meeting.' },
      { status: 404 },
    )
  }

  const { data: subscribers, error: subError } = await supabase
    .from('email_subscribers')
    .select('id, email, name, unsubscribe_token')
    .eq('status', 'active')
    .eq('city_fips', RICHMOND_FIPS)

  if (subError) {
    return NextResponse.json({ error: 'Failed to fetch subscribers' }, { status: 500 })
  }

  if (!subscribers || subscribers.length === 0) {
    return NextResponse.json({ sent: 0, failed: 0, reason: 'no active subscribers' })
  }

  const results = await Promise.allSettled(
    subscribers.map(async (sub) => {
      const unsubscribeUrl = `${BASE_URL}/api/subscribe?token=${sub.unsubscribe_token as string}`
      const { subject, html, text } = buildRecapEmail(
        {
          id: meeting.id as string,
          meeting_date: meeting.meeting_date as string,
          meeting_type: meeting.meeting_type as string,
          meeting_recap: broadcastRecapText,
          minutes_url: meeting.minutes_url as string | null,
        },
        unsubscribeUrl,
        broadcastRecapSource === 'transcript' ? 'transcript' : undefined,
      )
      return sendEmail({ to: sub.email as string, subject, html, text })
    }),
  )

  const sent = results.filter((r) => r.status === 'fulfilled' && r.value.success).length
  const failed = results.length - sent

  // Record send timestamp
  const now = new Date().toISOString()
  await supabase
    .from('meetings')
    .update({ recap_emailed_at: now })
    .eq('id', meetingId)

  if (failed > 0) {
    const errors = results
      .filter((r): r is PromiseRejectedResult | PromiseFulfilledResult<{ success: false; error?: string }> =>
        r.status === 'rejected' || (r.status === 'fulfilled' && !r.value.success),
      )
      .slice(0, 3)
      .map((r) => r.status === 'rejected' ? String(r.reason) : (r as PromiseFulfilledResult<{ error?: string }>).value.error)
    console.error(`Operator recap send: ${failed} failures for meeting ${meetingId}:`, errors)
  }

  return NextResponse.json({
    sent,
    failed,
    total_subscribers: subscribers.length,
    emailed_at: now,
  })
}
