import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import { CONFIDENCE_PUBLISHED } from '@/lib/thresholds'
import { isOperatorAuthenticated } from '@/lib/operator-auth'
import { getSupabaseAdmin } from '@/lib/supabase-admin'

const RICHMOND_FIPS = '0660620'
const MAX_BULK_FLAGS = 1000
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const unavailable = (bulk = false) => NextResponse.json({ error: 'Published connections are temporarily unavailable.' },
  { status: 503, headers: { 'Cache-Control': bulk ? 'private, no-store' : 'no-store' } })

/** Individual UUID details retain public RLS eligibility. The bulk list is used
 * only by the operator's financial-connections page and authenticates first.
 * Confidence is the existing display threshold; it is not operator approval.
 * Votes are intentionally absent: flags do not identify an operative motion,
 * and a subset of officials cannot establish council unanimity.
 */
export async function GET(request: NextRequest) {
  const flagId = request.nextUrl.searchParams.get('id')
  const all = request.nextUrl.searchParams.get('all')
  if (flagId && all) return NextResponse.json({ error: 'Choose id or all, not both' },
    { status: 400, headers: { 'Cache-Control': 'private, no-store' } })
  if (flagId && !UUID.test(flagId)) {
    return NextResponse.json({ error: 'Invalid flag ID' }, { status: 400, headers: { 'Cache-Control': 'no-store' } })
  }
  if (!flagId && !all) return NextResponse.json({ error: 'Missing id or all parameter' }, { status: 400 })
  try {
    if (flagId) {
      const { data, error } = await supabase.from('conflict_flags')
        .select('description, evidence, confidence_factors, scanner_version')
        .eq('id', flagId).eq('city_fips', RICHMOND_FIPS).eq('is_current', true)
        .gte('confidence', CONFIDENCE_PUBLISHED).not('false_positive', 'is', true)
        .maybeSingle()
      if (error) return unavailable()
      if (!data) return NextResponse.json({ error: 'Published flag not found' }, { status: 404, headers: { 'Cache-Control': 'no-store' } })
      return NextResponse.json(data, { headers: { 'Cache-Control': 'no-store' } })
    }
    if (!(await isOperatorAuthenticated())) return NextResponse.json({ error: 'Unauthorized' },
      { status: 401, headers: { 'Cache-Control': 'private, no-store' } })
    // Admin avoids recursive public RLS work, so explicitly retain both source
    // meeting checks and agenda retirement eligibility from migration 133.
    const { data: flags, count, error } = await getSupabaseAdmin().from('conflict_flags')
      .select(`id, flag_type, confidence, meeting_id, agenda_item_id, official_id,
        city_fips, is_current, false_positive,
        meetings!inner(id, meeting_date, city_fips, source_cancelled_at),
        agenda_items!inner(id, meeting_id, title, item_number, category, agenda_source_retired_at,
          source_meeting:meetings!inner(id, city_fips, source_cancelled_at)), officials!inner(id, name)`, { count: 'exact' })
      .eq('city_fips', RICHMOND_FIPS).eq('is_current', true)
      .gte('confidence', CONFIDENCE_PUBLISHED).not('false_positive', 'is', true)
      .eq('meetings.city_fips', RICHMOND_FIPS).is('meetings.source_cancelled_at', null)
      .is('agenda_items.agenda_source_retired_at', null)
      .eq('agenda_items.source_meeting.city_fips', RICHMOND_FIPS).is('agenda_items.source_meeting.source_cancelled_at', null)
      .order('confidence', { ascending: false }).order('id', { ascending: true }).limit(MAX_BULK_FLAGS)
    if (error || !Array.isArray(flags) || count === null || count > MAX_BULK_FLAGS || flags.length !== count) return unavailable(true)
    const seen = new Set<string>()
    const rows = flags.map(flag => {
      const meeting = flag.meetings as unknown as { id: string; meeting_date: string; city_fips: string; source_cancelled_at: string | null }
      const item = flag.agenda_items as unknown as { id: string; meeting_id: string; title: string; item_number: string; category: string | null;
        agenda_source_retired_at: string | null; source_meeting: { id: string; city_fips: string; source_cancelled_at: string | null } }
      const official = flag.officials as unknown as { id: string; name: string }
      if (!flag.id || seen.has(flag.id) || flag.city_fips !== RICHMOND_FIPS || flag.is_current !== true
        || flag.confidence < CONFIDENCE_PUBLISHED || !Number.isFinite(flag.confidence) || flag.false_positive === true
        || !meeting || meeting.id !== flag.meeting_id || meeting.city_fips !== RICHMOND_FIPS || meeting.source_cancelled_at !== null
        || !item || item.id !== flag.agenda_item_id || item.meeting_id !== flag.meeting_id || item.agenda_source_retired_at !== null
        || !item.source_meeting || item.source_meeting.id !== item.meeting_id
        || item.source_meeting.city_fips !== RICHMOND_FIPS || item.source_meeting.source_cancelled_at !== null
        || !official || official.id !== flag.official_id || typeof official.name !== 'string') {
        throw new Error('Flag list source eligibility changed')
      }
      seen.add(flag.id)
      return {
        id: flag.id, flag_type: flag.flag_type, confidence: flag.confidence,
        meeting_id: flag.meeting_id, meeting_date: meeting.meeting_date,
        agenda_item_id: flag.agenda_item_id, agenda_item_title: item.title,
        agenda_item_number: item.item_number, agenda_item_category: item.category,
        official_name: official.name, official_slug: official.name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, ''),
        official_id: flag.official_id,
      }
    })
    return NextResponse.json(rows, { headers: { 'Cache-Control': 'private, no-store' } })
  } catch {
    return unavailable(Boolean(all))
  }
}
