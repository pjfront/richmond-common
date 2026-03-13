import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'

const RICHMOND_FIPS = '0660620'

/**
 * GET /api/flag-details?id=<flag_id>
 *
 * Returns the description and evidence for a single conflict flag.
 * Used for on-demand loading when expanding table rows, keeping the
 * initial page payload small.
 */
export async function GET(request: NextRequest) {
  const flagId = request.nextUrl.searchParams.get('id')

  if (!flagId) {
    return NextResponse.json({ error: 'Missing id parameter' }, { status: 400 })
  }

  const { data, error } = await supabase
    .from('conflict_flags')
    .select('description, evidence')
    .eq('id', flagId)
    .eq('city_fips', RICHMOND_FIPS)
    .single()

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }

  if (!data) {
    return NextResponse.json({ error: 'Flag not found' }, { status: 404 })
  }

  return NextResponse.json({
    description: data.description,
    evidence: data.evidence,
  })
}
