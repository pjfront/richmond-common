import { NextRequest, NextResponse } from 'next/server'
import { getSupabaseAdmin } from '@/lib/supabase-admin'
import { sendEmail, buildDigestEmail } from '@/lib/email'

const RICHMOND_FIPS = '0660620'
const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://richmondcommons.org'

/**
 * Send a weekly digest email to all active subscribers.
 *
 * POST /api/email/send-digest
 * Body: { "days_back": 7 }  (optional, defaults to 7)
 * Auth: Bearer API_SECRET
 *
 * Collects all meetings with recaps from the last N days and sends
 * a single digest email. Returns early if no meetings have recaps.
 */
export async function POST(request: NextRequest) {
  // Auth
  const secret = request.headers.get('authorization')?.replace('Bearer ', '')
  if (!secret || secret !== process.env.API_SECRET) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const body = await request.json().catch(() => ({})) as Record<string, unknown>
  const daysBack = typeof body.days_back === 'number' && body.days_back > 0 ? body.days_back : 7

  const supabase = getSupabaseAdmin()

  // Fetch recent meetings with recaps
  const cutoff = new Date()
  cutoff.setDate(cutoff.getDate() - daysBack)
  const cutoffStr = cutoff.toISOString().split('T')[0]

  const { data: meetings, error: meetingError } = await supabase
    .from('meetings')
    .select('id, meeting_date, meeting_type, meeting_recap, minutes_url')
    .eq('city_fips', RICHMOND_FIPS)
    .not('meeting_recap', 'is', null)
    .gte('meeting_date', cutoffStr)
    .order('meeting_date', { ascending: false })

  if (meetingError) {
    console.error('Failed to fetch meetings for digest:', meetingError)
    return NextResponse.json({ error: 'Failed to fetch meetings' }, { status: 500 })
  }

  if (!meetings || meetings.length === 0) {
    return NextResponse.json({ sent: 0, reason: 'no meetings with recaps in the last ' + daysBack + ' days' })
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
    return NextResponse.json({ sent: 0, meeting_count: meetings.length, reason: 'no active subscribers' })
  }

  // Type the meetings for buildDigestEmail
  const typedMeetings = meetings.map((m) => ({
    id: m.id as string,
    meeting_date: m.meeting_date as string,
    meeting_type: m.meeting_type as string,
    meeting_recap: m.meeting_recap as string,
    minutes_url: m.minutes_url as string | null,
  }))

  // Send digest to all subscribers
  const results = await Promise.allSettled(
    subscribers.map(async (sub) => {
      const unsubscribeUrl = `${BASE_URL}/api/subscribe?token=${sub.unsubscribe_token as string}`
      const { subject, html, text } = buildDigestEmail(typedMeetings, unsubscribeUrl)
      return sendEmail({ to: sub.email as string, subject, html, text })
    }),
  )

  const sent = results.filter((r) => r.status === 'fulfilled' && r.value.success).length
  const failed = results.length - sent

  if (failed > 0) {
    console.error(`Digest email: ${failed} failures out of ${results.length}`)
  }

  console.log(`Digest email sent: ${sent} sent, ${failed} failed, ${meetings.length} meetings included`)

  return NextResponse.json({
    days_back: daysBack,
    meeting_count: meetings.length,
    sent,
    failed,
    total_subscribers: subscribers.length,
  })
}
