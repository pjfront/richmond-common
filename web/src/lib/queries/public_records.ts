import { cache } from 'react'
import { readCompleteRecords } from '../complete-record-read'
import type { NextRequestRequest, PublicRecordsStats, DepartmentCompliance } from '../types'
import { supabase, RICHMOND_FIPS, COLS_PUBLIC_RECORD_LIST } from './_shared'

const isClosed = (row: NextRequestRequest) => ['closed', 'completed'].includes((row.status ?? '').trim().toLowerCase())

/** Closure is an observed portal status, not a legal response/compliance finding. */
export function summarizePublicRecords(requests: NextRequestRequest[]): PublicRecordsStats {
  const closed = requests.filter(isClosed)
  const durations = closed.map(row => row.days_to_close)
    .filter((days): days is number => typeof days === 'number' && Number.isInteger(days) && days >= 0)
  return {
    totalRequests: requests.length,
    closedRequests: closed.length,
    notClosedRequests: requests.length - closed.length,
    closureTimingCount: durations.length,
    avgClosureDays: durations.length ? Math.round(durations.reduce((sum, days) => sum + days, 0) / durations.length) : null,
  }
}

/** One complete bounded read supplies the list and every displayed statistic.
 * React cache deduplicates callers within a render, without persisting failures.
 * Never infer complete totals from a server-capped page or a failed query.
 */
export const getPublicRecordsSnapshot = cache(async (cityFips = RICHMOND_FIPS) => {
  const rows = await readCompleteRecords('Public records', (from, to) => supabase.from('nextrequest_requests')
    .select(COLS_PUBLIC_RECORD_LIST, { count: 'exact' })
    .eq('city_fips', cityFips).is('source_removed_at', null)
    .order('submitted_date', { ascending: false }).order('id', { ascending: true }).range(from, to))
  const requests = rows as unknown as NextRequestRequest[]
  const grouped = new Map<string, NextRequestRequest[]>()
  for (const row of requests) {
    const department = row.department || 'Unknown'
    const group = grouped.get(department) ?? []
    group.push(row)
    grouped.set(department, group)
  }
  const departments: DepartmentCompliance[] = [...grouped].map(([department, rows]) => {
    const stats = summarizePublicRecords(rows)
    return { department, requestCount: rows.length, closedCount: stats.closedRequests,
      closureTimingCount: stats.closureTimingCount, avgClosureDays: stats.avgClosureDays }
  }).sort((a, b) => b.requestCount - a.requestCount || a.department.localeCompare(b.department))
  return { requests, stats: summarizePublicRecords(requests), departments }
})
