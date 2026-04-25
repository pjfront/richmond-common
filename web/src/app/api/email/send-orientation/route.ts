import { NextRequest, NextResponse } from 'next/server'
import { getSupabaseAdmin } from '@/lib/supabase-admin'
import { sendEmail, buildOrientationEmail } from '@/lib/email'

const RICHMOND_FIPS = '0660620'
const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://richmondcommons.org'

interface OrientationRow {
  id: string
  meeting_date: string
  orientation_preview: string
  agenda_url: string | null
}

interface SendResult {
  meeting_id: string
  meeting_date: string
  sent: number
  failed: number
  total_subscribers: number
  emailed_at: string
}

/**
 * Send pre-meeting orientation preview emails to all active subscribers.
 *
 * POST /api/email/send-orientation
 * Body: { "meeting_id": "uuid" }   // single meeting (optional)
 * Body: {}                         // discover mode: send for all upcoming
 *                                  // regular meetings with a generated
 *                                  // preview that haven't been emailed yet
 * Auth: Bearer API_SECRET
 *
 * Idempotent: skips meetings where orientation_emailed_at is already set.
 * Filters to meeting_type='regular' and meeting_date >= today so backfilled
 * orientations on past or non-council meetings are never broadcast.
 */
export async function POST(request: NextRequest) {
  const secret = request.headers.get('authorization')?.replace('Bearer ', '')
  if (!secret || secret !== process.env.API_SECRET) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const body = await request.json().catch(() => ({})) as Record<string, unknown>
  const meetingId = typeof body.meeting_id === 'string' ? body.meeting_id.trim() : ''

  const supabase = getSupabaseAdmin()
  const today = new Date().toISOString().split('T')[0]

  let candidates: OrientationRow[] = []

  if (meetingId) {
    const { data, error } = await supabase
      .from('meetings')
      .select('id, meeting_date, orientation_preview, agenda_url, orientation_emailed_at')
      .eq('id', meetingId)
      .single()

    if (error || !data) {
      return NextResponse.json({ error: 'Meeting not found' }, { status: 404 })
    }
    if (!data.orientation_preview) {
      return NextResponse.json(
        { error: 'No orientation preview generated for this meeting yet.' },
        { status: 404 },
      )
    }
    if (data.orientation_emailed_at) {
      return NextResponse.json({
        meeting_id: meetingId,
        sent: 0,
        skipped: true,
        reason: 'already emailed',
        emailed_at: data.orientation_emailed_at,
      })
    }
    candidates = [{
      id: data.id as string,
      meeting_date: data.meeting_date as string,
      orientation_preview: data.orientation_preview as string,
      agenda_url: data.agenda_url as string | null,
    }]
  } else {
    const { data, error } = await supabase
      .from('meetings')
      .select('id, meeting_date, orientation_preview, agenda_url')
      .eq('city_fips', RICHMOND_FIPS)
      .eq('meeting_type', 'regular')
      .gte('meeting_date', today)
      .not('orientation_preview', 'is', null)
      .is('orientation_emailed_at', null)
      .order('meeting_date', { ascending: true })

    if (error) {
      console.error('Failed to fetch orientation candidates:', error)
      return NextResponse.json({ error: 'Failed to fetch meetings' }, { status: 500 })
    }
    candidates = (data ?? []).map((m) => ({
      id: m.id as string,
      meeting_date: m.meeting_date as string,
      orientation_preview: m.orientation_preview as string,
      agenda_url: m.agenda_url as string | null,
    }))
  }

  if (candidates.length === 0) {
    return NextResponse.json({ sent: 0, results: [], reason: 'no candidates' })
  }

  const results: SendResult[] = []

  for (const meeting of candidates) {
    // Per-meeting subscriber filter: skip subscribers who already received this
    // meeting's orientation at signup (last_orientation_meeting_id == meeting.id).
    const { data: subscribers, error: subError } = await supabase
      .from('email_subscribers')
      .select('id, email, name, unsubscribe_token, last_orientation_meeting_id')
      .eq('status', 'active')
      .eq('city_fips', RICHMOND_FIPS)
      .or(`last_orientation_meeting_id.is.null,last_orientation_meeting_id.neq.${meeting.id}`)

    if (subError) {
      console.error('Failed to fetch subscribers:', subError)
      return NextResponse.json({ error: 'Failed to fetch subscribers' }, { status: 500 })
    }

    if (!subscribers || subscribers.length === 0) {
      results.push({
        meeting_id: meeting.id,
        meeting_date: meeting.meeting_date,
        sent: 0,
        failed: 0,
        total_subscribers: 0,
        emailed_at: '',
      })
      continue
    }

    const sendResults = await Promise.allSettled(
      subscribers.map(async (sub) => {
        const unsubscribeUrl = `${BASE_URL}/api/subscribe?token=${sub.unsubscribe_token as string}`
        const { subject, html, text } = buildOrientationEmail(meeting, unsubscribeUrl)
        const result = await sendEmail({ to: sub.email as string, subject, html, text })
        return { sub_id: sub.id as string, ...result }
      }),
    )

    const successfulIds: string[] = []
    let failed = 0
    for (const r of sendResults) {
      if (r.status === 'fulfilled' && r.value.success) {
        successfulIds.push(r.value.sub_id)
      } else {
        failed += 1
      }
    }
    const sent = successfulIds.length

    if (failed > 0) {
      const errors = sendResults
        .filter((r): r is PromiseRejectedResult | PromiseFulfilledResult<{ sub_id: string; success: false; error?: string }> =>
          r.status === 'rejected' || (r.status === 'fulfilled' && !r.value.success),
        )
        .slice(0, 3)
        .map((r) => r.status === 'rejected' ? String(r.reason) : (r as PromiseFulfilledResult<{ error?: string }>).value.error)
      console.error(`Orientation email: ${failed} failures for meeting ${meeting.id}:`, errors)
    }

    const now = new Date().toISOString()
    // Only mark as sent when at least one delivery succeeded — if every send
    // failed, leave the timestamp NULL so the next run retries.
    if (sent > 0) {
      await supabase
        .from('meetings')
        .update({ orientation_emailed_at: now })
        .eq('id', meeting.id)
      await supabase
        .from('email_subscribers')
        .update({ last_orientation_meeting_id: meeting.id })
        .in('id', successfulIds)
    }

    console.log(`Orientation email for ${meeting.meeting_date} (${meeting.id}): ${sent} sent, ${failed} failed`)

    results.push({
      meeting_id: meeting.id,
      meeting_date: meeting.meeting_date,
      sent,
      failed,
      total_subscribers: subscribers.length,
      emailed_at: now,
    })
  }

  const totalSent = results.reduce((sum, r) => sum + r.sent, 0)
  const totalFailed = results.reduce((sum, r) => sum + r.failed, 0)

  return NextResponse.json({
    candidates: candidates.length,
    sent: totalSent,
    failed: totalFailed,
    results,
  })
}
