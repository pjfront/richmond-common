import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'

const RICHMOND_FIPS = '0660620'
const CONFIDENCE_PUBLISHED = 0.5

/**
 * GET /api/flag-details?id=<flag_id>
 *   Returns description + evidence for a single flag (on-demand expand).
 *
 * GET /api/flag-details?all=1
 *   Returns all published flags as lightweight rows (no description/evidence).
 *   Used by the client-side table to avoid a 167KB RSC payload.
 */
export async function GET(request: NextRequest) {
  const flagId = request.nextUrl.searchParams.get('id')
  const all = request.nextUrl.searchParams.get('all')

  // Single flag detail
  if (flagId) {
    const { data, error } = await supabase
      .from('conflict_flags')
      .select('description, evidence')
      .eq('id', flagId)
      .eq('city_fips', RICHMOND_FIPS)
      .single()

    if (error) return NextResponse.json({ error: error.message }, { status: 500 })
    if (!data) return NextResponse.json({ error: 'Flag not found' }, { status: 404 })

    return NextResponse.json({
      description: data.description,
      evidence: data.evidence,
    })
  }

  // All published flags (lightweight)
  if (all) {
    const { data: flags, error } = await supabase
      .from('conflict_flags')
      .select(`
        id, flag_type, confidence,
        meeting_id, agenda_item_id, official_id,
        meetings!inner(meeting_date),
        agenda_items!inner(title, item_number, category),
        officials!inner(name)
      `)
      .eq('city_fips', RICHMOND_FIPS)
      .eq('is_current', true)
      .gte('confidence', CONFIDENCE_PUBLISHED)
      .order('confidence', { ascending: false })
      .limit(1000)

    if (error) return NextResponse.json({ error: error.message }, { status: 500 })
    if (!flags) return NextResponse.json([])

    // Build lightweight rows with joined fields flattened
    const rows = flags.map((f) => {
      const meeting = f.meetings as unknown as { meeting_date: string }
      const item = f.agenda_items as unknown as { title: string; item_number: string; category: string | null }
      const official = f.officials as unknown as { name: string }
      const slug = official.name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '')

      return {
        id: f.id,
        flag_type: f.flag_type,
        confidence: f.confidence,
        meeting_id: f.meeting_id,
        meeting_date: meeting.meeting_date,
        agenda_item_id: f.agenda_item_id,
        agenda_item_title: item.title,
        agenda_item_number: item.item_number,
        agenda_item_category: item.category,
        official_name: official.name,
        official_slug: slug,
        official_id: f.official_id,
      }
    })

    return NextResponse.json(rows, {
      headers: { 'Cache-Control': 'public, s-maxage=3600, stale-while-revalidate=86400' },
    })
  }

  return NextResponse.json({ error: 'Missing id or all parameter' }, { status: 400 })
}
