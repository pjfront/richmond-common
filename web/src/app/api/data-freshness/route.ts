import { NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import type { DataSourceFreshness } from '@/lib/types'

const RICHMOND_FIPS = '0660620'

// Staleness thresholds in days (from cloud-pipeline-spec.md)
const FRESHNESS_THRESHOLDS: Record<string, number> = {
  netfile: 14,
  calaccess: 45,
  escribemeetings: 7,
  archive_center: 60,
  nextrequest: 7,
  socrata_payroll: 45,
  socrata_expenditures: 45,
}

export async function GET() {
  // Only the most recent completed run per source matters for freshness.
  // Bounding to the last 180 days (2x the largest threshold) and capping
  // rows keeps this query bounded as data_sync_log accumulates. Sources
  // stale beyond the window still surface as is_stale=true (just with a
  // null days_since_sync). Pre-2026-05 this query had no cap and was one
  // of the contributors to the Supabase I/O quota pause.
  const cutoffDate = new Date()
  cutoffDate.setDate(cutoffDate.getDate() - 180)
  const cutoff = cutoffDate.toISOString()
  const { data: rows, error } = await supabase
    .from('data_sync_log')
    .select('source, completed_at')
    .eq('city_fips', RICHMOND_FIPS)
    .eq('status', 'completed')
    .gte('completed_at', cutoff)
    .order('completed_at', { ascending: false })
    .limit(500)

  if (error) {
    return NextResponse.json(
      { error: 'Failed to query sync data' },
      { status: 500 },
    )
  }

  // Build a map of source -> most recent completed_at
  const syncMap = new Map<string, string>()
  for (const row of rows ?? []) {
    if (row.source && row.completed_at && !syncMap.has(row.source)) {
      syncMap.set(row.source, row.completed_at)
    }
  }

  const now = Date.now()
  const results: DataSourceFreshness[] = Object.entries(FRESHNESS_THRESHOLDS).map(
    ([source, thresholdDays]) => {
      const lastSync = syncMap.get(source) ?? null
      if (lastSync) {
        const daysSince =
          (now - new Date(lastSync).getTime()) / (1000 * 60 * 60 * 24)
        return {
          source,
          last_sync: lastSync,
          threshold_days: thresholdDays,
          days_since_sync: Math.round(daysSince * 10) / 10,
          is_stale: daysSince > thresholdDays,
        }
      }
      return {
        source,
        last_sync: null,
        threshold_days: thresholdDays,
        days_since_sync: null,
        is_stale: true, // Never synced = stale
      }
    },
  )

  const staleCount = results.filter((r) => r.is_stale).length

  return NextResponse.json(
    { sources: results, stale_count: staleCount, total: results.length },
    {
      headers: {
        'Cache-Control': 'public, s-maxage=3600, stale-while-revalidate=7200',
      },
    },
  )
}
