import { NextRequest, NextResponse } from 'next/server'
import { getSupabaseAdmin } from '@/lib/supabase-admin'
import { sendEmail, buildRecapEmail, buildTranscriptRecapEmail } from '@/lib/email'

const RICHMOND_FIPS = '0660620'
const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://richmondcommons.org'

/**
 * Send a meeting recap email to all active subscribers.
 *
 * POST /api/email/send-recap
 * Body: { "meeting_id": "uuid" }
 * Auth: Bearer API_SECRET
 *
 * Operator-only endpoint — called manually or via automation after
 * generate_meeting_recaps.py populates meetings.meeting_recap.
 */
export async function POST(request: NextRequest) {
  // Auth
  const secret = request.headers.get('authorization')?.replace('Bearer ', '')
  if (!secret || secret !== process.env.API_SECRET) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const body = await request.json().catch(() => ({})) as Record<string, unknown>
  const meetingId = typeof body.meeting_id === 'string' ? body.meeting_id.trim() : ''
  const recapType = typeof body.type === 'string' ? body.type : 'vote'

  if (!meetingId) {
    return NextResponse.json({ error: 'meeting_id is required' }, { status: 400 })
  }

  const supabase = getSupabaseAdmin()

  // Fetch meeting with recap fields
  const { data: meeting, error: meetingError } = await supabase
    .from('meetings')
    .select('id, meeting_date, meeting_type, meeting_recap, transcript_recap, transcript_recap_source, minutes_url')
    .eq('id', meetingId)
    .single()

  if (meetingError || !meeting) {
    return NextResponse.json({ error: 'Meeting not found' }, { status: 404 })
  }

  const useTranscript = recapType === 'transcript'
  const recapContent = useTranscript ? meeting.transcript_recap : meeting.meeting_recap

  if (!recapContent) {
    const hint = useTranscript
      ? 'No transcript recap available. Run generate_transcript_recaps.py first.'
      : 'No recap available. Run generate_meeting_recaps.py first.'
    return NextResponse.json({ error: hint }, { status: 404 })
  }

  // Fetch active subscribers
  const { data: subscribers, error: subError } = await supabase
    .from('email_subscribers')
    .select('id, email, name, unsubscribe_token')
    .eq('status', 'active')
    .eq('city_fips', RICHMOND_FIPS)

  if (subError) {
    console.error('Failed to fetch subscribers:', subError)
    return NextResponse.json({ error: 'Failed to fetch subscribers' }, { status: 500 })
  }

  if (!subscribers || subscribers.length === 0) {
    return NextResponse.json({ meeting_id: meetingId, sent: 0, failed: 0, reason: 'no active subscribers' })
  }

  // Send to all subscribers in parallel
  const results = await Promise.allSettled(
    subscribers.map(async (sub) => {
      const unsubscribeUrl = `${BASE_URL}/api/subscribe?token=${sub.unsubscribe_token as string}`

      const email = useTranscript
        ? buildTranscriptRecapEmail(
            {
              id: meeting.id as string,
              meeting_date: meeting.meeting_date as string,
              meeting_type: meeting.meeting_type as string,
              transcript_recap: meeting.transcript_recap as string,
              transcript_recap_source: meeting.transcript_recap_source as string | null,
            },
            unsubscribeUrl,
          )
        : buildRecapEmail(
            {
              id: meeting.id as string,
              meeting_date: meeting.meeting_date as string,
              meeting_type: meeting.meeting_type as string,
              meeting_recap: meeting.meeting_recap as string,
              minutes_url: meeting.minutes_url as string | null,
            },
            unsubscribeUrl,
          )

      return sendEmail({ to: sub.email as string, subject: email.subject, html: email.html, text: email.text })
    }),
  )

  const sent = results.filter((r) => r.status === 'fulfilled' && r.value.success).length
  const failed = results.length - sent

  if (failed > 0) {
    const errors = results
      .filter((r): r is PromiseRejectedResult | PromiseFulfilledResult<{ success: false; error?: string }> =>
        r.status === 'rejected' || (r.status === 'fulfilled' && !r.value.success),
      )
      .slice(0, 3)
      .map((r) => r.status === 'rejected' ? String(r.reason) : (r as PromiseFulfilledResult<{ error?: string }>).value.error)
    console.error(`Recap email: ${failed} failures for meeting ${meetingId}:`, errors)
  }

  console.log(`Recap email sent for meeting ${meetingId}: ${sent} sent, ${failed} failed`)

  return NextResponse.json({
    meeting_id: meetingId,
    meeting_date: meeting.meeting_date,
    sent,
    failed,
    total_subscribers: subscribers.length,
  })
}
