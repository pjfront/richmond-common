import { NextRequest, NextResponse } from 'next/server'
import { getSupabaseAdmin } from '@/lib/supabase-admin'
import { buildOrientationEmail } from '@/lib/email'
import {
  areAllDeliveriesSent,
  broadcastTrackedEmail,
  loadActiveSubscribers,
} from '@/lib/email-delivery'
import type { Provenance } from '@/lib/types'

const RICHMOND_FIPS = '0660620'
const MAX_ORIENTATION_CANDIDATES = 20

interface OrientationRow {
  id: string
  meeting_date: string
  orientation_preview: string
  orientation_preview_provenance: Provenance | null
  agenda_url: string | null
}
/** Per-recipient idempotent pre-meeting orientation delivery. */
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
      .select('id, meeting_date, orientation_preview, orientation_preview_provenance, agenda_url')
      .eq('id', meetingId)
      .is('source_cancelled_at', null)
      .single()
    if (error || !data) {
      return NextResponse.json({ error: 'Meeting not found' }, { status: 404 })
    }
    if (!data.orientation_preview) {
      return NextResponse.json({ error: 'No orientation preview generated.' }, { status: 404 })
    }
    candidates = [{
      id: data.id as string,
      meeting_date: data.meeting_date as string,
      orientation_preview: data.orientation_preview as string,
      orientation_preview_provenance: (data.orientation_preview_provenance ?? null) as Provenance | null,
      agenda_url: data.agenda_url as string | null,
    }]
  } else {
    // Do not filter on the legacy meeting timestamp. The delivery ledger must
    // see the candidate so it can retry only the recipients that failed.
    const { data, error } = await supabase
      .from('meetings')
      .select('id, meeting_date, orientation_preview, orientation_preview_provenance, agenda_url')
      .eq('city_fips', RICHMOND_FIPS)
      .eq('meeting_type', 'regular')
      .gte('meeting_date', today)
      .is('source_cancelled_at', null)
      .not('orientation_preview', 'is', null)
      .order('meeting_date', { ascending: true })
      .limit(MAX_ORIENTATION_CANDIDATES)
    if (error) {
      return NextResponse.json({ error: 'Failed to fetch meetings' }, { status: 500 })
    }
    candidates = (data ?? []).map((meeting) => ({
      id: meeting.id as string,
      meeting_date: meeting.meeting_date as string,
      orientation_preview: meeting.orientation_preview as string,
      orientation_preview_provenance: (meeting.orientation_preview_provenance ?? null) as Provenance | null,
      agenda_url: meeting.agenda_url as string | null,
    }))
  }

  if (candidates.length === 0) {
    return NextResponse.json({ sent: 0, results: [], reason: 'no candidates' })
  }

  try {
    const subscribers = await loadActiveSubscribers(supabase, RICHMOND_FIPS)
    const results = []
    for (const meeting of candidates) {
      const result = await broadcastTrackedEmail({
        supabase,
        subscribers,
        kind: 'orientation',
        contentKey: `meeting:${meeting.id}`,
        build: (_subscriber, { unsubscribeUrl, manageUrl }) => buildOrientationEmail(
          meeting,
          unsubscribeUrl,
          manageUrl,
        ),
      })

      // Compatibility/display only. Failures remain retryable because the next
      // discovery call still selects this meeting and consults the ledger.
      let emailedAt: string | null = null
      const fullyDelivered = await areAllDeliveriesSent(
        supabase,
        subscribers,
        'orientation',
        `meeting:${meeting.id}`,
      )
      if (fullyDelivered) {
        emailedAt = new Date().toISOString()
        const { error } = await supabase
          .from('meetings')
          .update({ orientation_emailed_at: emailedAt })
          .eq('id', meeting.id)
        if (error) emailedAt = null
      }
      results.push({
        meeting_id: meeting.id,
        meeting_date: meeting.meeting_date,
        emailed_at: emailedAt,
        fully_delivered: fullyDelivered,
        ...result,
      })
    }

    return NextResponse.json({
      candidates: candidates.length,
      sent: results.reduce((sum, result) => sum + result.sent, 0),
      failed: results.reduce((sum, result) => sum + result.failed, 0),
      skipped: results.reduce((sum, result) => sum + result.skipped, 0),
      results,
    })
  } catch (deliveryError) {
    return NextResponse.json(
      { error: deliveryError instanceof Error ? deliveryError.message : 'Delivery failed' },
      { status: 503 },
    )
  }
}
