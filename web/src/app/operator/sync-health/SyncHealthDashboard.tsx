'use client'

import { Fragment, useEffect, useState } from 'react'
import OperatorGate from '@/components/OperatorGate'

const SOURCE_LABELS: Record<string, string> = {
  netfile: 'NetFile (Local Contributions)',
  calaccess: 'CAL-ACCESS (State PACs/IEs)',
  escribemeetings: 'eSCRIBE (Meeting Agendas)',
  archive_center: 'Archive Center (Minutes)',
  minutes_extraction: 'Minutes Extraction (Claude)',
  nextrequest: 'NextRequest (CPRA)',
  socrata_payroll: 'Socrata (Payroll)',
  socrata_expenditures: 'Socrata (Expenditures)',
  socrata_permits: 'Socrata (Permits)',
  socrata_licenses: 'Socrata (Licenses)',
  socrata_code_cases: 'Socrata (Code Enforcement)',
  socrata_service_requests: 'Socrata (Service Requests)',
  socrata_projects: 'Socrata (Development Projects)',
  form700: 'Form 700 (Economic Interests)',
  form803_behested: 'Form 803 (Behested Payments)',
  lobbyist_registrations: 'Lobbyist Registrations',
  propublica: 'ProPublica (Nonprofits)',
}

const CADENCE_LABELS: Record<string, string> = {
  daily: 'Daily',
  weekly: 'Weekly (Mon)',
  monthly: 'Monthly (15th)',
  quarterly: 'Quarterly (Jan/Apr/Jul/Oct)',
}

const CADENCE_ORDER: Record<string, number> = {
  daily: 0,
  weekly: 1,
  monthly: 2,
  quarterly: 3,
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

interface SyncHealthResponse {
  sources: SourceHealth[]
  summary: {
    total: number
    stale_count: number
    failing_count: number
    total_syncs_30d: number
    overall_status: 'healthy' | 'warning' | 'alert'
  }
  checked_at: string
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    healthy: 'bg-green-100 text-green-800 border-green-200',
    warning: 'bg-amber-100 text-amber-800 border-amber-200',
    alert: 'bg-red-100 text-red-800 border-red-200',
  }
  return (
    <span
      className={`inline-block px-3 py-1 rounded-full text-sm font-semibold border ${styles[status] ?? styles.warning}`}
    >
      {status.toUpperCase()}
    </span>
  )
}

function CadenceBadge({ cadence }: { cadence: string }) {
  const styles: Record<string, string> = {
    daily: 'bg-purple-100 text-purple-700 border-purple-200',
    weekly: 'bg-blue-100 text-blue-700 border-blue-200',
    monthly: 'bg-teal-100 text-teal-700 border-teal-200',
    quarterly: 'bg-slate-100 text-slate-600 border-slate-200',
  }
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium border ${styles[cadence] ?? styles.weekly}`}>
      {CADENCE_LABELS[cadence] ?? cadence}
    </span>
  )
}

function RunStatusDot({ status }: { status: string }) {
  const color = status === 'completed' ? 'bg-green-500' : status === 'failed' ? 'bg-red-500' : 'bg-amber-500'
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${color}`}
      title={status}
    />
  )
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return 'Never'
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function formatDays(days: number | null): string {
  if (days === null) return '—'
  if (days < 1) return '<1d'
  return `${Math.round(days)}d`
}

function FreshnessBar({ daysSince, threshold }: { daysSince: number | null; threshold: number }) {
  if (daysSince === null) {
    return <div className="w-full h-2 bg-red-300 rounded-full" title="Never synced" />
  }
  const pct = Math.min((daysSince / threshold) * 100, 100)
  const color = pct > 100 ? 'bg-red-500' : pct > 75 ? 'bg-amber-400' : 'bg-green-500'
  return (
    <div className="w-full h-2 bg-slate-200 rounded-full overflow-hidden" title={`${Math.round(daysSince)}d / ${threshold}d threshold`}>
      <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${Math.min(pct, 100)}%` }} />
    </div>
  )
}

function SourceRow({ source, expanded, onToggle }: { source: SourceHealth; expanded: boolean; onToggle: () => void }) {
  const label = SOURCE_LABELS[source.source] ?? source.source
  const rowBg = source.is_stale
    ? 'bg-red-50 hover:bg-red-100'
    : source.failure_count_30d > 0
      ? 'bg-amber-50 hover:bg-amber-100'
      : 'hover:bg-slate-50'

  return (
    <>
      <tr className={`cursor-pointer transition-colors ${rowBg}`} onClick={onToggle}>
        <td className="px-4 py-3">
          <div className="font-medium text-sm text-slate-800">{label}</div>
          <div className="text-xs text-slate-500 mt-0.5">
            <CadenceBadge cadence={source.cadence} />
          </div>
        </td>
        <td className="px-4 py-3 w-40">
          <FreshnessBar daysSince={source.days_since_sync} threshold={source.threshold_days} />
          <div className="text-xs text-slate-500 mt-1">
            {formatDays(source.days_since_sync)} / {source.threshold_days}d
          </div>
        </td>
        <td className="px-4 py-3 text-sm text-slate-600">
          {formatDate(source.last_sync)}
        </td>
        <td className="px-4 py-3 text-center">
          {source.last_status === 'completed' ? (
            <span className="text-green-600 text-sm">OK</span>
          ) : source.last_status === 'failed' ? (
            <span className="text-red-600 text-sm font-medium">FAILED</span>
          ) : source.last_status ? (
            <span className="text-amber-600 text-sm">{source.last_status}</span>
          ) : (
            <span className="text-slate-400 text-sm">—</span>
          )}
        </td>
        <td className="px-4 py-3 text-center text-sm">
          {source.failure_count_30d > 0 ? (
            <span className="text-red-600 font-medium">{source.failure_count_30d}</span>
          ) : (
            <span className="text-slate-400">0</span>
          )}
        </td>
        <td className="px-4 py-3 text-center text-sm text-slate-500">
          {source.records_last_run !== null ? source.records_last_run.toLocaleString() : '—'}
        </td>
        <td className="px-4 py-3 text-center">
          <span className="text-slate-400 text-xs">{expanded ? '▼' : '▶'}</span>
        </td>
      </tr>
      {expanded && source.recent_runs.length > 0 && (
        <tr>
          <td colSpan={7} className="px-4 py-2 bg-slate-50 border-t border-slate-100">
            <div className="text-xs font-medium text-slate-500 mb-2">Recent runs</div>
            <div className="space-y-1">
              {source.recent_runs.map((run) => (
                <div key={run.id} className="flex items-center gap-3 text-xs text-slate-600">
                  <RunStatusDot status={run.status} />
                  <span className="w-36">{formatDate(run.started_at)}</span>
                  <span className="w-16">{run.status}</span>
                  <span className="w-20">{run.triggered_by ?? '—'}</span>
                  {run.records_fetched !== null && (
                    <span className="text-slate-400">
                      {run.records_fetched} fetched
                      {run.records_new !== null && run.records_new > 0 ? `, ${run.records_new} new` : ''}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

function SummaryCards({ summary }: { summary: SyncHealthResponse['summary'] }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="text-xs font-medium text-slate-500">Sources Tracked</div>
        <div className="text-2xl font-bold text-slate-800 mt-1">{summary.total}</div>
      </div>
      <div className={`rounded-lg border p-4 ${summary.stale_count > 0 ? 'border-red-200 bg-red-50' : 'border-green-200 bg-green-50'}`}>
        <div className="text-xs font-medium text-slate-500">Stale Sources</div>
        <div className={`text-2xl font-bold mt-1 ${summary.stale_count > 0 ? 'text-red-700' : 'text-green-700'}`}>
          {summary.stale_count}
        </div>
      </div>
      <div className={`rounded-lg border p-4 ${summary.failing_count > 0 ? 'border-amber-200 bg-amber-50' : 'border-green-200 bg-green-50'}`}>
        <div className="text-xs font-medium text-slate-500">Sources with Failures (30d)</div>
        <div className={`text-2xl font-bold mt-1 ${summary.failing_count > 0 ? 'text-amber-700' : 'text-green-700'}`}>
          {summary.failing_count}
        </div>
      </div>
      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="text-xs font-medium text-slate-500">Total Syncs (30d)</div>
        <div className="text-2xl font-bold text-slate-800 mt-1">{summary.total_syncs_30d}</div>
      </div>
    </div>
  )
}

function Dashboard() {
  const [data, setData] = useState<SyncHealthResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedSource, setExpandedSource] = useState<string | null>(null)
  const [groupByCadence, setGroupByCadence] = useState(false)

  useEffect(() => {
    fetch('/api/operator/sync-health')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((d) => setData(d as SyncHealthResponse))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <div className="text-center py-12 text-slate-500">Loading sync health data...</div>
  }
  if (error || !data) {
    return (
      <div className="text-center py-12 text-red-600">
        Failed to load sync health: {error ?? 'unknown error'}
      </div>
    )
  }

  const sources = groupByCadence
    ? [...data.sources].sort((a, b) => {
        const cadenceA = CADENCE_ORDER[a.cadence] ?? 99
        const cadenceB = CADENCE_ORDER[b.cadence] ?? 99
        if (cadenceA !== cadenceB) return cadenceA - cadenceB
        return (a.days_until_stale ?? 999) - (b.days_until_stale ?? 999)
      })
    : data.sources

  // Group headers for cadence view
  let lastCadence = ''

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-civic-navy">Sync Health Dashboard</h1>
          <p className="text-sm text-slate-500 mt-1">
            Pipeline sync status across all {data.summary.total} data sources.
            Checked {new Date(data.checked_at).toLocaleTimeString()}.
          </p>
        </div>
        <StatusBadge status={data.summary.overall_status} />
      </div>

      <SummaryCards summary={data.summary} />

      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold text-slate-800">Source Status</h2>
        <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
          <input
            type="checkbox"
            checked={groupByCadence}
            onChange={(e) => setGroupByCadence(e.target.checked)}
            className="rounded border-slate-300"
          />
          Group by schedule
        </label>
      </div>

      <div className="border border-slate-200 rounded-lg overflow-hidden">
        <table className="w-full text-left">
          <thead className="bg-slate-100 border-b border-slate-200">
            <tr>
              <th className="px-4 py-2 text-xs font-semibold text-slate-500">Source</th>
              <th className="px-4 py-2 text-xs font-semibold text-slate-500 w-40">Freshness</th>
              <th className="px-4 py-2 text-xs font-semibold text-slate-500">Last Sync</th>
              <th className="px-4 py-2 text-xs font-semibold text-slate-500 text-center">Status</th>
              <th className="px-4 py-2 text-xs font-semibold text-slate-500 text-center">Failures</th>
              <th className="px-4 py-2 text-xs font-semibold text-slate-500 text-center">Records</th>
              <th className="px-4 py-2 text-xs font-semibold text-slate-500 w-8"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {sources.map((source) => {
              const showCadenceHeader = groupByCadence && source.cadence !== lastCadence
              if (showCadenceHeader) lastCadence = source.cadence

              return showCadenceHeader ? (
                <Fragment key={`group-${source.source}`}>
                  <tr className="bg-slate-50">
                    <td colSpan={7} className="px-4 py-2 text-xs font-bold text-slate-600 uppercase tracking-wide">
                      {CADENCE_LABELS[source.cadence] ?? source.cadence}
                    </td>
                  </tr>
                  <SourceRow
                    source={source}
                    expanded={expandedSource === source.source}
                    onToggle={() => setExpandedSource(expandedSource === source.source ? null : source.source)}
                  />
                </Fragment>
              ) : (
                <SourceRow
                  key={source.source}
                  source={source}
                  expanded={expandedSource === source.source}
                  onToggle={() => setExpandedSource(expandedSource === source.source ? null : source.source)}
                />
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function SyncHealthDashboard() {
  return (
    <OperatorGate
      fallback={
        <div className="max-w-4xl mx-auto py-12 text-center text-slate-500">
          Sync health monitoring is available to operators only.
        </div>
      }
    >
      <div className="max-w-6xl mx-auto px-4 py-8">
        <Dashboard />
      </div>
    </OperatorGate>
  )
}
