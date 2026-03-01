'use client'

import { useEffect, useState } from 'react'
import MeetingCompletenessTable from '@/components/MeetingCompletenessTable'
import type { DataQualityResponse, DataSourceFreshness, DataAnomaly } from '@/lib/types'

const SOURCE_LABELS: Record<string, string> = {
  netfile: 'NetFile (Local Campaign Finance)',
  calaccess: 'CAL-ACCESS (State Campaign Finance)',
  escribemeetings: 'eSCRIBE (Meeting Agendas)',
  archive_center: 'Archive Center (Minutes/Docs)',
  nextrequest: 'NextRequest (Public Records)',
  socrata_payroll: 'Socrata (Payroll)',
  socrata_expenditures: 'Socrata (Expenditures)',
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

function FreshnessCard({ source }: { source: DataSourceFreshness }) {
  const label = SOURCE_LABELS[source.source] ?? source.source
  const staleClass = source.is_stale
    ? 'border-red-200 bg-red-50'
    : 'border-green-200 bg-green-50'

  let syncText = 'Never synced'
  if (source.last_sync) {
    const d = new Date(source.last_sync)
    syncText = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  }

  return (
    <div className={`rounded-lg border p-3 ${staleClass}`}>
      <div className="text-xs font-medium text-slate-500 mb-1 truncate" title={label}>
        {label}
      </div>
      <div className="flex items-center justify-between">
        <span className="text-sm text-slate-700">{syncText}</span>
        {source.is_stale ? (
          <span className="text-xs font-medium text-red-700">
            {source.days_since_sync !== null ? `${Math.round(source.days_since_sync)}d ago` : 'Never'}
          </span>
        ) : (
          <span className="text-xs font-medium text-green-700">
            {source.days_since_sync !== null ? `${Math.round(source.days_since_sync)}d ago` : 'OK'}
          </span>
        )}
      </div>
      <div className="text-[10px] text-slate-400 mt-1">
        Threshold: {source.threshold_days}d
      </div>
    </div>
  )
}

function CoverageStat({
  label,
  count,
  percentage,
}: {
  label: string
  count: number
  percentage: number
}) {
  let color = 'text-green-700'
  if (percentage < 50) color = 'text-red-700'
  else if (percentage < 80) color = 'text-amber-700'

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
      <div className="text-2xl font-bold text-slate-900">{percentage}%</div>
      <div className="text-sm text-slate-500">{label}</div>
      <div className="text-xs text-slate-400 mt-1">{count} meetings</div>
    </div>
  )
}

function AnomalyCard({ anomaly }: { anomaly: DataAnomaly }) {
  const isAlert = anomaly.severity === 'alert'
  const borderColor = isAlert ? 'border-red-300 bg-red-50' : 'border-amber-300 bg-amber-50'
  const icon = isAlert ? '!!' : '!'

  return (
    <div className={`rounded-lg border p-3 ${borderColor}`}>
      <div className="flex items-start gap-2">
        <span
          className={`text-xs font-bold px-1.5 py-0.5 rounded ${
            isAlert ? 'bg-red-200 text-red-800' : 'bg-amber-200 text-amber-800'
          }`}
        >
          {icon}
        </span>
        <div>
          <div className="text-sm font-medium text-slate-900">
            <a href={`/meetings/${anomaly.meeting_id}`} className="hover:underline">
              {anomaly.meeting_date}
            </a>
            {' '}&middot;{' '}
            <span className="text-slate-500">{anomaly.anomaly_type.replace(/_/g, ' ')}</span>
          </div>
          <div className="text-xs text-slate-600 mt-0.5">{anomaly.description}</div>
        </div>
      </div>
    </div>
  )
}

export default function DataQualityDashboard() {
  const [data, setData] = useState<DataQualityResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/data-quality')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then((json: DataQualityResponse) => {
        setData(json)
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <h1 className="text-3xl font-bold text-slate-900 mb-2">Data Quality Dashboard</h1>
        <p className="text-slate-500">Loading data quality metrics...</p>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <h1 className="text-3xl font-bold text-slate-900 mb-2">Data Quality Dashboard</h1>
        <p className="text-red-600">Failed to load data quality metrics: {error}</p>
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="flex items-center gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Data Quality Dashboard</h1>
          <p className="text-slate-500 text-sm mt-1">
            Freshness, completeness, and anomaly monitoring.
            {' '}Checked {new Date(data.checked_at).toLocaleString('en-US', {
              month: 'short',
              day: 'numeric',
              hour: 'numeric',
              minute: '2-digit',
            })}
          </p>
        </div>
        <StatusBadge status={data.overall_status} />
      </div>

      {/* Anomalies (top of page if any exist) */}
      {data.anomalies.length > 0 && (
        <section className="mb-8">
          <h2 className="text-lg font-semibold text-slate-900 mb-3">
            Anomalies ({data.anomalies.length})
          </h2>
          <div className="grid gap-2">
            {data.anomalies.map((a, i) => (
              <AnomalyCard key={`${a.meeting_id}-${a.anomaly_type}-${i}`} anomaly={a} />
            ))}
          </div>
        </section>
      )}

      {/* Source Freshness */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold text-slate-900 mb-3">
          Source Freshness
          {data.freshness.stale_count > 0 && (
            <span className="ml-2 text-sm font-normal text-red-600">
              {data.freshness.stale_count} stale
            </span>
          )}
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {data.freshness.sources.map((s) => (
            <FreshnessCard key={s.source} source={s} />
          ))}
        </div>
      </section>

      {/* Document Coverage */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold text-slate-900 mb-3">
          Document Coverage
          <span className="ml-2 text-sm font-normal text-slate-500">
            ({data.completeness.total_meetings} meetings)
          </span>
        </h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <CoverageStat
            label="Minutes URL"
            count={data.completeness.document_coverage.minutes.count}
            percentage={data.completeness.document_coverage.minutes.percentage}
          />
          <CoverageStat
            label="Agenda URL"
            count={data.completeness.document_coverage.agenda.count}
            percentage={data.completeness.document_coverage.agenda.percentage}
          />
          <CoverageStat
            label="Video URL"
            count={data.completeness.document_coverage.video.count}
            percentage={data.completeness.document_coverage.video.percentage}
          />
        </div>
      </section>

      {/* Meeting Completeness Table */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold text-slate-900 mb-1">
          Recent Meeting Completeness
        </h2>
        <p className="text-sm text-slate-500 mb-3">
          {data.completeness.complete_meetings} of {data.completeness.recent_meetings.length} recent
          meetings have full data (items + votes + attendance).
        </p>
        <div className="bg-white rounded-lg border border-slate-200">
          <MeetingCompletenessTable data={data.completeness.recent_meetings} />
        </div>
      </section>

      {/* No anomalies message */}
      {data.anomalies.length === 0 && (
        <p className="text-sm text-green-600 italic">No anomalies detected in recent meetings.</p>
      )}
    </div>
  )
}
