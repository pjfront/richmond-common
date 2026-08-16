import { NextRequest, NextResponse } from 'next/server'
import { getSupabaseAdmin } from '@/lib/supabase-admin'
import { sendRecapBroadcast } from '@/lib/email-delivery'
import type { Provenance } from '@/lib/types'

/** API_SECRET-authenticated recap delivery. Repeated calls skip successes. */
export async function POST(request: NextRequest) {
  const secret = request.headers.get('authorization')?.replace('Bearer ', '')
  if (!secret || secret !== process.env.API_SECRET) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const body = await request.json().catch(() => ({})) as Record<string, unknown>
  const meetingId = typeof body.meeting_id === 'string' ? body.meeting_id.trim() : ''
  if (!meetingId) {
    return NextResponse.json({ error: 'meeting_id is required' }, { status: 400 })
  }

  const supabase = getSupabaseAdmin()
  const { data: meeting, error } = await supabase
    .from('meetings')
    .select('id, meeting_date, meeting_type, meeting_recap, meeting_recap_provenance, minutes_url, recap_emailed_at, transcript_recap_emailed_at')
    .eq('id', meetingId)
    .single()

  if (error || !meeting) {
    return NextResponse.json({ error: 'Meeting not found' }, { status: 404 })
  }
  if (!meeting.meeting_recap) {
    return NextResponse.json({ error: 'No recap available for this meeting.' }, { status: 404 })
  }
  const legacyEmailedAt = (meeting.recap_emailed_at
    ?? meeting.transcript_recap_emailed_at) as string | null
  if (legacyEmailedAt) {
    return NextResponse.json({
      meeting_id: meetingId,
      meeting_date: meeting.meeting_date,
      sent: 0,
      already_sent: true,
      legacy_already_sent: true,
      emailed_at: legacyEmailedAt,
      reason: 'legacy recap delivery marker is already set',
    })
  }

  try {
    const result = await sendRecapBroadcast(supabase, {
      id: meeting.id as string,
      meeting_date: meeting.meeting_date as string,
      meeting_type: meeting.meeting_type as string,
      meeting_recap: meeting.meeting_recap as string,
      minutes_url: meeting.minutes_url as string | null,
      meeting_recap_provenance: (meeting.meeting_recap_provenance ?? null) as Provenance | null,
      source: 'minutes',
      recap_emailed_at: null,
      transcript_recap_emailed_at: null,
    })
    return NextResponse.json({
      meeting_id: meetingId,
      meeting_date: meeting.meeting_date,
      ...result,
    }, { status: result.fully_delivered ? 200 : 503 })
  } catch (deliveryError) {
    return NextResponse.json(
      { error: deliveryError instanceof Error ? deliveryError.message : 'Delivery failed' },
      { status: 503 },
    )
  }
}
