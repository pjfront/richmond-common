import { NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import type {
  PendingDecision,
  DecisionSeverity,
  DecisionQueueResponse,
} from '@/lib/types'

const RICHMOND_FIPS = '0660620'

// Severity ranking for ordering (matches Python CASE expression)
const SEVERITY_RANK: Record<DecisionSeverity, number> = {
  critical: 1,
  high: 2,
  medium: 3,
  low: 4,
  info: 5,
}

export async function GET() {
  try {
    // Run pending and resolved queries in parallel
    const [pendingResult, resolvedResult] = await Promise.all([
      supabase
        .from('pending_decisions')
        .select('*')
        .eq('city_fips', RICHMOND_FIPS)
        .eq('status', 'pending')
        .order('created_at', { ascending: false }),

      supabase
        .from('pending_decisions')
        .select('*')
        .eq('city_fips', RICHMOND_FIPS)
        .neq('status', 'pending')
        .order('resolved_at', { ascending: false })
        .limit(20),
    ])

    if (pendingResult.error) throw pendingResult.error
    if (resolvedResult.error) throw resolvedResult.error

    const pending = (pendingResult.data ?? []) as PendingDecision[]
    const resolved = (resolvedResult.data ?? []) as PendingDecision[]

    // Sort pending by severity rank then age (oldest first within rank)
    pending.sort((a, b) => {
      const rankA = SEVERITY_RANK[a.severity] ?? 5
      const rankB = SEVERITY_RANK[b.severity] ?? 5
      if (rankA !== rankB) return rankA - rankB
      return new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
    })

    // Count by severity
    const counts: Record<DecisionSeverity, number> = {
      critical: 0,
      high: 0,
      medium: 0,
      low: 0,
      info: 0,
    }
    for (const d of pending) {
      if (d.severity in counts) {
        counts[d.severity]++
      }
    }

    const response: DecisionQueueResponse = {
      summary: {
        total_pending: pending.length,
        counts,
      },
      pending,
      recently_resolved: resolved,
    }

    // No caching — operator data should always be fresh
    return NextResponse.json(response)
  } catch (err) {
    console.error('Decision queue fetch failed:', err)
    return NextResponse.json(
      { error: 'Failed to fetch decision queue' },
      { status: 500 },
    )
  }
}
