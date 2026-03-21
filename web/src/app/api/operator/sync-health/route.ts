import { NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'

const RICHMOND_FIPS = '0660620'

/**
 * Staleness thresholds in days — must match src/staleness_monitor.py
 * FRESHNESS_THRESHOLDS. Single source of truth is Python; this mirrors it.
 */
const FRESHNESS_THRESHOLDS: Record<string, number> = {
  netfile: 14,
  calaccess: 45,
  escribemeetings: 7,
  archive_center: 45,
  nextrequest: 7,
  socrata_payroll: 45,
  socrata_expenditures: 45,
  socrata_permits: 30,
  socrata_licenses: 45,
  socrata_code_cases: 30,
  socrata_service_requests: 30,
  socrata_projects: 45,
  form700: 90,
  minutes_extraction: 14,
  form803_behested: 90,
  lobbyist_registrations: 90,
  propublica: 120,
}

/** Which cadence tier each source belongs to */
const SCHEDULE_CADENCE: Record<string, string> = {
  nextrequest: 'daily',
  archive_center: 'weekly',
  minutes_extraction: 'weekly',
  escribemeetings: 'weekly',
  netfile: 'weekly',
  socrata_payroll: 'weekly',
  socrata_expenditures: 'weekly',
  calaccess: 'monthly',
  socrata_permits: 'monthly',
  socrata_licenses: 'monthly',
  socrata_code_cases: 'monthly',
  socrata_service_requests: 'monthly',
  socrata_projects: 'monthly',
  form700: 'quarterly',
  form803_behested: 'quarterly',
  lobbyist_registrations: 'quarterly',
  propublica: 'quarterly',
}

interface SyncRun {
  id: string
  source: string
  status: string
  started_at: string
  completed_at: string | null
  records_fetched: number | null
  records_new: number | null
  records_updated: number | null
  triggered_by: string | null
}

interface SourceHealth {
  source: string
  threshold_days: number
  cadence: string
  last_sync: string | null
  last_status: string | null
  days_since_sync: number | null
  is_stale: boolean
  days_until_stale: number | null
  recent_runs: SyncRun[]
  records_last_run: number | null
  failure_count_30d: number
}

export async function GET() {
  // Fetch all sync log entries for the last 90 days (covers quarterly sources)
  const ninetyDaysAgo = new Date(Date.now() - 90 * 24 * 60 * 60 * 1000).toISOString()

  const { data: rows, error } = await supabase
    .from('data_sync_log')
    .select('id, source, status, started_at, completed_at, records_fetched, records_new, records_updated, triggered_by')
    .eq('city_fips', RICHMOND_FIPS)
    .gte('started_at', ninetyDaysAgo)
    .order('started_at', { ascending: false })

  if (error) {
    return NextResponse.json(
      { error: 'Failed to query sync data' },
      { status: 500 },
    )
  }

  const allRuns = (rows ?? []) as SyncRun[]
  const now = Date.now()
  const thirtyDaysAgo = now - 30 * 24 * 60 * 60 * 1000

  const sources: SourceHealth[] = Object.entries(FRESHNESS_THRESHOLDS).map(
    ([source, thresholdDays]) => {
      const sourceRuns = allRuns.filter((r) => r.source === source)
      const completedRuns = sourceRuns.filter((r) => r.status === 'completed')
      const lastCompleted = completedRuns[0] ?? null
      const lastRun = sourceRuns[0] ?? null

      const lastSync = lastCompleted?.completed_at ?? null
      const daysSince = lastSync
        ? (now - new Date(lastSync).getTime()) / (1000 * 60 * 60 * 24)
        : null

      const isStale = daysSince === null || daysSince > thresholdDays
      const daysUntilStale = daysSince !== null
        ? Math.round((thresholdDays - daysSince) * 10) / 10
        : null

      // Count failures in last 30 days
      const recentFailures = sourceRuns.filter(
        (r) => r.status === 'failed' && new Date(r.started_at).getTime() > thirtyDaysAgo,
      ).length

      return {
        source,
        threshold_days: thresholdDays,
        cadence: SCHEDULE_CADENCE[source] ?? 'unknown',
        last_sync: lastSync,
        last_status: lastRun?.status ?? null,
        days_since_sync: daysSince !== null ? Math.round(daysSince * 10) / 10 : null,
        is_stale: isStale,
        days_until_stale: daysUntilStale,
        recent_runs: sourceRuns.slice(0, 5),
        records_last_run: lastCompleted?.records_fetched ?? null,
        failure_count_30d: recentFailures,
      }
    },
  )

  // Sort: stale first, then by days_until_stale ascending (closest to stale first)
  sources.sort((a, b) => {
    if (a.is_stale !== b.is_stale) return a.is_stale ? -1 : 1
    if (a.days_until_stale !== null && b.days_until_stale !== null) {
      return a.days_until_stale - b.days_until_stale
    }
    return 0
  })

  const staleCount = sources.filter((s) => s.is_stale).length
  const failingCount = sources.filter((s) => s.failure_count_30d > 0).length
  const totalSyncs30d = allRuns.filter(
    (r) => new Date(r.started_at).getTime() > thirtyDaysAgo,
  ).length

  const overallStatus = staleCount > 3 ? 'alert' : staleCount > 0 ? 'warning' : 'healthy'

  return NextResponse.json(
    {
      sources,
      summary: {
        total: sources.length,
        stale_count: staleCount,
        failing_count: failingCount,
        total_syncs_30d: totalSyncs30d,
        overall_status: overallStatus,
      },
      checked_at: new Date().toISOString(),
    },
    {
      headers: {
        'Cache-Control': 'public, s-maxage=300, stale-while-revalidate=600',
      },
    },
  )
}
