import { NextRequest, NextResponse } from 'next/server'
import { getSupabaseAdmin } from '@/lib/supabase-admin'
import { sendRecapBroadcast } from '@/lib/email-delivery'
import {
  RECAP_SOURCE_COLUMNS,
  selectPersistedRecap,
  type PersistedRecapSource,
} from '@/lib/email-content-source'

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
    .select(RECAP_SOURCE_COLUMNS)
    .eq('id', meetingId)
    .single()

  if (error || !meeting) {
    return NextResponse.json({ error: 'Meeting not found' }, { status: 404 })
  }
  const recap = selectPersistedRecap(meeting as unknown as PersistedRecapSource)
  if (!recap) {
    return NextResponse.json({ error: 'No recap available for this meeting.' }, { status: 404 })
  }
  const legacyEmailedAt = recap.recap_emailed_at
    ?? recap.transcript_recap_emailed_at
  if (legacyEmailedAt) {
    return NextResponse.json({
      meeting_id: meetingId,
      meeting_date: recap.meeting_date,
      sent: 0,
      already_sent: true,
      legacy_already_sent: true,
      emailed_at: legacyEmailedAt,
      reason: 'legacy recap delivery marker is already set',
    })
  }

  try {
    const result = await sendRecapBroadcast(supabase, recap)
    return NextResponse.json({
      meeting_id: meetingId,
      meeting_date: recap.meeting_date,
      ...result,
    }, { status: result.fully_delivered ? 200 : 503 })
  } catch (deliveryError) {
    return NextResponse.json(
      { error: deliveryError instanceof Error ? deliveryError.message : 'Delivery failed' },
      { status: 503 },
    )
  }
}
