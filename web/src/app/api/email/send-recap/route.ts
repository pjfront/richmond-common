import { NextRequest, NextResponse } from 'next/server'
import { getSupabaseAdmin } from '@/lib/supabase-admin'
import { sendEmail, buildRecapEmail } from '@/lib/email'

const RICHMOND_FIPS = '0660620'
const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://richmondcommons.org'

/**
 * POST /api/email/send-recap
 *
 * Send a meeting recap email to all active subscribers.
 * Requires API_SECRET header for authentication (operator-only).
 *
 * Body: { meeting_id: string }
 */
export async function POST(request: NextRequest) {
  // Authenticate — require API_SECRET
  const apiSecret = process.env.API_SECRET
  if (!apiSecret) {
    return NextResponse.json({ error: 'API_SECRET not configured' }, { status: 500 })
  }
  const authHeader = request.headers.get('authorization')
  if (authHeader !== `Bearer ${apiSecret}`) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  try {
    const body = (await request.json()) as Record<string, unknown>
    const meetingId = body.meeting_id
    if (typeof meetingId !== 'string' || !meetingId) {
      return NextResponse.json({ error: 'meeting_id is required' }, { status: 400 })
    }

    const supabase = getSupabaseAdmin()

    // ─── Fetch meeting with recap ───────────────────────────
    const { data: meeting, error: meetingError } = await supabase
      .from('meetings')
      .select('id, meeting_date, meeting_type, meeting_recap')
      .eq('id', meetingId)
      .eq('city_fips', RICHMOND_FIPS)
      .single()

    if (meetingError || !meeting) {
      return NextResponse.json({ error: 'Meeting not found' }, { status: 404 })
    }

    const recap = meeting.meeting_recap as string | null
    if (!recap) {
      return NextResponse.json(
        { error: 'Meeting has no recap yet. Run generate_meeting_recaps.py first.' },
        { status: 422 },
      )
    }

    // ─── Fetch meeting stats ────────────────────────────────
    const [itemResult, voteResult, commentResult] = await Promise.all([
      supabase
        .from('agenda_items')
        .select('id', { count: 'exact', head: true })
        .eq('meeting_id', meetingId),
      supabase
        .from('motions')
        .select('id', { count: 'exact', head: true })
        .in(
          'agenda_item_id',
          // Subquery: get item IDs for this meeting
          (
            await supabase
              .from('agenda_items')
              .select('id')
              .eq('meeting_id', meetingId)
          ).data?.map((i) => i.id as string) ?? [],
        ),
      supabase
        .from('public_comments')
        .select('id', { count: 'exact', head: true })
        .eq('meeting_id', meetingId),
    ])

    // ─── Format meeting date ────────────────────────────────
    const meetingDate = new Date(meeting.meeting_date as string)
    const formattedDate = meetingDate.toLocaleDateString('en-US', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      timeZone: 'America/Los_Angeles',
    })

    const meetingType = (meeting.meeting_type as string) || 'City Council Meeting'

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

    // ─── Send emails ────────────────────────────────────────
    const recapData = {
      meetingDate: formattedDate,
      meetingType,
      meetingId: meeting.id as string,
      recap,
      itemCount: itemResult.count ?? 0,
      voteCount: voteResult.count ?? 0,
      commentCount: commentResult.count ?? 0,
    }

    let sent = 0
    let failed = 0
    const errors: string[] = []

    for (const sub of subscribers) {
      const token = sub.unsubscribe_token as string
      const unsubscribeUrl = `${BASE_URL}/api/subscribe?token=${token}`
      const manageUrl = `${BASE_URL}/subscribe/manage?token=${token}`
      const email = buildRecapEmail(
        recapData,
        sub.name as string | null,
        unsubscribeUrl,
        manageUrl,
      )

      const result = await sendEmail({ to: sub.email as string, ...email })
      if (result.success) {
        sent++
      } else {
        failed++
        errors.push(`${sub.email}: ${result.error}`)
      }

      // Small delay to respect Resend rate limits (10/sec on free tier)
      if (subscribers.length > 5) {
        await new Promise((resolve) => setTimeout(resolve, 150))
      }
    }

    return NextResponse.json({
      sent,
      failed,
      total: subscribers.length,
      meeting_date: formattedDate,
      meeting_type: meetingType,
      ...(errors.length > 0 ? { errors } : {}),
    })
  } catch (err) {
    console.error('Send recap error:', err)
    return NextResponse.json({ error: 'Internal error' }, { status: 500 })
  }
}
