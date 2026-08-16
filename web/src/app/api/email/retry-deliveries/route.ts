import { NextRequest, NextResponse } from 'next/server'
import { retryPendingEmailDeliveries } from '@/lib/email-delivery'
import { getSupabaseAdmin } from '@/lib/supabase-admin'

/** Scheduled, bounded recovery for due welcome and orientation deliveries. */
export async function POST(request: NextRequest) {
  const secret = request.headers.get('authorization')?.replace('Bearer ', '')
  if (!secret || secret !== process.env.API_SECRET) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  try {
    const supabase = getSupabaseAdmin()
    const { data: pruned, error: pruneError } = await supabase.rpc(
      'prune_subscription_activations',
    )
    if (pruneError) {
      throw new Error(`Failed to enforce activation retention: ${pruneError.message}`)
    }

    const result = await retryPendingEmailDeliveries(supabase)
    return NextResponse.json({
      ...result,
      activations_pruned: typeof pruned === 'number' ? pruned : 0,
    }, {
      status: result.fully_resolved ? 200 : 503,
    })
  } catch (deliveryError) {
    return NextResponse.json(
      { error: deliveryError instanceof Error ? deliveryError.message : 'Email recovery failed' },
      { status: 503 },
    )
  }
}
