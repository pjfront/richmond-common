import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import { CONFIDENCE_PUBLISHED } from '@/lib/thresholds'

const RICHMOND_FIPS = '0660620'
const MAX_PUBLIC_FLAGS = 1000
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const unavailable = () => NextResponse.json({ error: 'Published connections are temporarily unavailable.' },
  { status: 503, headers: { 'Cache-Control': 'no-store' } })

/** Identical public predicates apply to list and UUID lookup.
 * Confidence is the existing display threshold; it is not operator approval.
 * Votes are intentionally absent: flags do not identify an operative motion,
 * and a subset of officials cannot establish council unanimity.
 */
export async function GET(request: NextRequest) {
  const flagId = request.nextUrl.searchParams.get('id')
  const all = request.nextUrl.searchParams.get('all')
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
    const { data: flags, count, error } = await supabase.from('conflict_flags')
      .select(`id, flag_type, confidence, meeting_id, agenda_item_id, official_id,
        meetings!inner(meeting_date), agenda_items!inner(title, item_number, category), officials!inner(name)`, { count: 'exact' })
      .eq('city_fips', RICHMOND_FIPS).eq('is_current', true)
      .gte('confidence', CONFIDENCE_PUBLISHED).not('false_positive', 'is', true)
      .order('confidence', { ascending: false }).order('id', { ascending: true }).limit(MAX_PUBLIC_FLAGS)
    if (error || !Array.isArray(flags) || count === null || count > MAX_PUBLIC_FLAGS || flags.length !== count) return unavailable()
    const rows = flags.map(flag => {
      const meeting = flag.meetings as unknown as { meeting_date: string }
      const item = flag.agenda_items as unknown as { title: string; item_number: string; category: string | null }
      const official = flag.officials as unknown as { name: string }
      return {
        id: flag.id, flag_type: flag.flag_type, confidence: flag.confidence,
        meeting_id: flag.meeting_id, meeting_date: meeting.meeting_date,
        agenda_item_id: flag.agenda_item_id, agenda_item_title: item.title,
        agenda_item_number: item.item_number, agenda_item_category: item.category,
        official_name: official.name, official_slug: official.name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, ''),
        official_id: flag.official_id,
        // Retain the existing client DTO without manufacturing vote statistics.
        vote_choice: null, motion_result: null, is_unanimous: null,
      }
    })
    return NextResponse.json(rows, { headers: { 'Cache-Control': 'public, s-maxage=300' } })
  } catch {
    return unavailable()
  }
}
