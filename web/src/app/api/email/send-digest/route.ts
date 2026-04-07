import { NextRequest, NextResponse } from 'next/server'
import { getSupabaseAdmin } from '@/lib/supabase-admin'
import { sendEmail, buildDigestEmail } from '@/lib/email'

const RICHMOND_FIPS = '0660620'
const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://richmondcommons.org'

/**
 * POST /api/email/send-digest
 *
 * Send a weekly digest email covering all meetings with recaps
 * from the past N days (default 7). Operator-only endpoint.
 *
 * Body: { days?: number }  (default 7)
 */
export async function POST(request: NextRequest) {
  // Authenticate
  const apiSecret = process.env.API_SECRET
  if (!apiSecret) {
    return NextResponse.json({ error: 'API_SECRET not configured' }, { status: 500 })
  }
  const authHeader = request.headers.get('authorization')
  if (authHeader !== `Bearer ${apiSecret}`) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
    const days = typeof body.days === 'number' && body.days > 0 ? body.days : 7

    const supabase = getSupabaseAdmin()

    // ─── Fetch recent meetings with recaps ──────────────────
    const since = new Date()
    since.setDate(since.getDate() - days)

    const { data: meetings, error: meetingError } = await supabase
      .from('meetings')
      .select('id, meeting_date, meeting_type, meeting_recap')
      .eq('city_fips', RICHMOND_FIPS)
      .not('meeting_recap', 'is', null)
      .gte('meeting_date', since.toISOString().split('T')[0])
      .order('meeting_date', { ascending: true })

    if (meetingError) {
      console.error('Failed to fetch meetings:', meetingError)
      return NextResponse.json({ error: 'Failed to fetch meetings' }, { status: 500 })
    }

    if (!meetings || meetings.length === 0) {
      return NextResponse.json({
        sent: 0,
        message: `No meetings with recaps in the last ${days} days`,
      })
    }

    // ─── Get item counts per meeting ────────────────────────
    const meetingIds = meetings.map((m) => m.id as string)
    const { data: itemCounts } = await supabase
      .from('agenda_items')
      .select('meeting_id')
      .in('meeting_id', meetingIds)

    const countByMeeting = new Map<string, number>()
    for (const row of itemCounts ?? []) {
      const mid = row.meeting_id as string
      countByMeeting.set(mid, (countByMeeting.get(mid) ?? 0) + 1)
    }

    // ─── Build digest meeting summaries ─────────────────────
    const digestMeetings = meetings.map((m) => {
      const meetingDate = new Date(m.meeting_date as string)
      return {
        meetingDate: meetingDate.toLocaleDateString('en-US', {
          weekday: 'long',
          month: 'long',
          day: 'numeric',
          timeZone: 'America/Los_Angeles',
        }),
        meetingType: (m.meeting_type as string) || 'City Council Meeting',
        meetingId: m.id as string,
        recap: m.meeting_recap as string,
        itemCount: countByMeeting.get(m.id as string) ?? 0,
      }
    })

    // ─── Week label ─────────────────────────────────────────
    const now = new Date()
    const weekLabel = `Week of ${now.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric', timeZone: 'America/Los_Angeles' })}`

    // ─── Fetch active subscribers ───────────────────────────
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
      return NextResponse.json({ sent: 0, message: 'No active subscribers' })
    }

    // ─── Send digest to each subscriber ─────────────────────
    let sent = 0
    let failed = 0
    const errors: string[] = []

    for (const sub of subscribers) {
      const token = sub.unsubscribe_token as string
      const unsubscribeUrl = `${BASE_URL}/api/subscribe?token=${token}`
      const manageUrl = `${BASE_URL}/subscribe/manage?token=${token}`
      const digest = buildDigestEmail(
        digestMeetings,
        weekLabel,
        sub.name as string | null,
        unsubscribeUrl,
        manageUrl,
      )

      const result = await sendEmail({ to: sub.email as string, ...digest })
      if (result.success) {
        sent++
      } else {
        failed++
        errors.push(`${sub.email}: ${result.error}`)
      }

      // Respect Resend rate limits
      if (subscribers.length > 5) {
        await new Promise((resolve) => setTimeout(resolve, 150))
      }
    }

    return NextResponse.json({
      sent,
      failed,
      total: subscribers.length,
      meetings_included: meetings.length,
      week_label: weekLabel,
      ...(errors.length > 0 ? { errors } : {}),
    })
  } catch (err) {
    console.error('Send digest error:', err)
    return NextResponse.json({ error: 'Internal error' }, { status: 500 })
  }
}
