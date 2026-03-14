import { NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'

// Temporary diagnostic endpoint — remove after fixing coalitions page
export async function GET() {
  try {
    // Test 1: Can we call the RPC?
    const startRpc = Date.now()
    const { data, error, count } = await supabase
      .rpc('get_contested_votes', { p_city_fips: '0660620' })

    if (error) {
      return NextResponse.json({
        status: 'rpc_error',
        error: {
          message: error.message,
          code: error.code,
          details: error.details,
          hint: error.hint,
        },
        elapsed_ms: Date.now() - startRpc,
      }, { status: 500 })
    }

    const rows = data ?? []

    // Test 2: Sample the data shape
    const sample = rows.slice(0, 3)
    const uniqueMotions = new Set(rows.map((r: Record<string, unknown>) => r.motion_id)).size
    const uniqueOfficials = new Set(rows.map((r: Record<string, unknown>) => r.official_id)).size

    return NextResponse.json({
      status: 'ok',
      row_count: rows.length,
      unique_motions: uniqueMotions,
      unique_officials: uniqueOfficials,
      elapsed_ms: Date.now() - startRpc,
      sample,
    })
  } catch (err) {
    return NextResponse.json({
      status: 'exception',
      error: err instanceof Error ? err.message : String(err),
      stack: err instanceof Error ? err.stack?.split('\n').slice(0, 5) : undefined,
    }, { status: 500 })
  }
}
