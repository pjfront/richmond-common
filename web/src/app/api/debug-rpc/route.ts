import { NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'

export const dynamic = 'force-dynamic'

export async function GET() {
  const cityFips = '0660620'

  // Test 1: Direct RPC call
  const { data: rpcData, error: rpcError } = await supabase.rpc('get_meeting_counts', {
    p_city_fips: cityFips,
  })

  // Test 2: Simple meetings query (control)
  const { data: meetings, error: meetingsError } = await supabase
    .from('meetings')
    .select('id')
    .eq('city_fips', cityFips)
    .limit(3)

  return NextResponse.json(
    {
      rpc: {
        success: !rpcError,
        error: rpcError ? { message: rpcError.message, code: rpcError.code, details: rpcError.details, hint: rpcError.hint } : null,
        rowCount: Array.isArray(rpcData) ? rpcData.length : null,
        sample: Array.isArray(rpcData) && rpcData.length > 0 ? rpcData[0] : null,
        rawType: typeof rpcData,
      },
      meetings: {
        success: !meetingsError,
        error: meetingsError?.message ?? null,
        count: Array.isArray(meetings) ? meetings.length : null,
      },
      env: {
        url: process.env.NEXT_PUBLIC_SUPABASE_URL ? 'set' : 'missing',
        key: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ? 'set' : 'missing',
      },
    },
    { headers: { 'Cache-Control': 'no-store' } }
  )
}
