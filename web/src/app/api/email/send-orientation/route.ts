import { NextRequest, NextResponse } from 'next/server'
import { getSupabaseAdmin } from '@/lib/supabase-admin'
import { buildOrientationEmail } from '@/lib/email'
import {
  areAllDeliveriesSent,
  broadcastTrackedEmail,
  loadActiveSubscribers,
} from '@/lib/email-delivery'
import {
  COUNCIL_ORIENTATION_SOURCE_COLUMNS,
  RICHMOND_COUNCIL_BODY_TYPE,
} from '@/lib/orientation-scope'
import { richmondDateKey } from '@/lib/richmond-date'
import type { Provenance } from '@/lib/types'

const RICHMOND_FIPS = '0660620'

interface OrientationRow {
  id: string
  meeting_date: string
  orientation_preview: string
  orientation_preview_provenance: Provenance | null
  agenda_url: string | null
  orientation_emailed_at: string | null
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
  const today = richmondDateKey()
  let candidates: OrientationRow[] = []

  if (meetingId) {
    const { data, error } = await supabase
      .from('meetings')
      .select(`${COUNCIL_ORIENTATION_SOURCE_COLUMNS}, orientation_emailed_at`)
      .eq('id', meetingId)
      .eq('city_fips', RICHMOND_FIPS)
      .eq('meeting_type', 'regular')
      .eq('bodies.body_type', RICHMOND_COUNCIL_BODY_TYPE)
      .gte('meeting_date', today)
      .is('source_cancelled_at', null)
      .single()
    if (error || !data) {
      return NextResponse.json({ error: 'Meeting not found' }, { status: 404 })
    }
    if (!data.orientation_preview) {
      return NextResponse.json({ error: 'No orientation preview generated.' }, { status: 404 })
    }
    if (data.orientation_emailed_at) {
      return NextResponse.json({
        meeting_id: meetingId,
        sent: 0,
        already_sent: true,
        reason: 'legacy meeting delivery marker is already set',
        emailed_at: data.orientation_emailed_at,
      })
    }
    candidates = [{
      id: data.id as string,
      meeting_date: data.meeting_date as string,
      orientation_preview: data.orientation_preview as string,
      orientation_preview_provenance: (data.orientation_preview_provenance ?? null) as Provenance | null,
      agenda_url: data.agenda_url as string | null,
      orientation_emailed_at: null,
    }]
  } else {
    // Process only the next unsent upcoming meeting. The legacy timestamp is
    // the cold-start cutover authority; the ledger handles partial retries for
    // a candidate whose marker remains NULL.
    const { data, error } = await supabase
      .from('meetings')
      .select(`${COUNCIL_ORIENTATION_SOURCE_COLUMNS}, orientation_emailed_at`)
      .eq('city_fips', RICHMOND_FIPS)
      .eq('meeting_type', 'regular')
      .eq('bodies.body_type', RICHMOND_COUNCIL_BODY_TYPE)
      .gte('meeting_date', today)
      .is('source_cancelled_at', null)
      .not('orientation_preview', 'is', null)
      .is('orientation_emailed_at', null)
      .order('meeting_date', { ascending: true })
      .limit(1)
    if (error) {
      return NextResponse.json({ error: 'Failed to fetch meetings' }, { status: 500 })
    }
    candidates = (data ?? []).map((meeting) => ({
      id: meeting.id as string,
      meeting_date: meeting.meeting_date as string,
      orientation_preview: meeting.orientation_preview as string,
      orientation_preview_provenance: (meeting.orientation_preview_provenance ?? null) as Provenance | null,
      agenda_url: meeting.agenda_url as string | null,
      orientation_emailed_at: null,
    }))
  }

  if (candidates.length === 0) {
    return NextResponse.json({
      sent: 0,
      results: [],
      reason: 'no orientation candidates',
    })
  }

  try {
    const subscribers = await loadActiveSubscribers(supabase, RICHMOND_FIPS, true)
    if (subscribers.length === 0) {
      return NextResponse.json({
        candidates: candidates.length,
        sent: 0,
        results: [],
        reason: 'no active subscribers',
      })
    }
    const results = []
    for (const meeting of candidates) {
      const eligibleSubscribers = subscribers.filter(
        (subscriber) => subscriber.last_orientation_meeting_id !== meeting.id,
      )
      const legacyAlreadySent = subscribers.length - eligibleSubscribers.length
      const result = await broadcastTrackedEmail({
        supabase,
        subscribers: eligibleSubscribers,
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
      const fullyDelivered = eligibleSubscribers.length === 0
        ? legacyAlreadySent > 0
        : await areAllDeliveriesSent(
          supabase,
          eligibleSubscribers,
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
        if (emailedAt && eligibleSubscribers.length > 0) {
          await supabase
            .from('email_subscribers')
            .update({ last_orientation_meeting_id: meeting.id })
            .in('id', eligibleSubscribers.map((subscriber) => subscriber.id))
        }
      }
      results.push({
        ...result,
        meeting_id: meeting.id,
        meeting_date: meeting.meeting_date,
        emailed_at: emailedAt,
        fully_delivered: fullyDelivered,
        already_sent: result.already_sent + legacyAlreadySent,
        legacy_already_sent: legacyAlreadySent,
      })
    }

    const response = {
      candidates: candidates.length,
      sent: results.reduce((sum, result) => sum + result.sent, 0),
      failed: results.reduce((sum, result) => sum + result.failed, 0),
      already_sent: results.reduce((sum, result) => sum + result.already_sent, 0),
      deferred: results.reduce((sum, result) => sum + result.deferred, 0),
      manual_review: results.reduce((sum, result) => sum + result.manual_review, 0),
      results,
    }
    return NextResponse.json(response, {
      status: results.every((result) => result.fully_delivered) ? 200 : 503,
    })
  } catch (deliveryError) {
    return NextResponse.json(
      { error: deliveryError instanceof Error ? deliveryError.message : 'Delivery failed' },
      { status: 503 },
    )
  }
}
