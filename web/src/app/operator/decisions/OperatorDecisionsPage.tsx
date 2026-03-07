'use client'

import { useEffect, useState } from 'react'
import OperatorGate from '@/components/OperatorGate'
import type { DecisionQueueResponse, PendingDecision, DecisionSeverity } from '@/lib/types'

const SEVERITY_STYLES: Record<DecisionSeverity, string> = {
  critical: 'bg-red-100 text-red-800 border-red-200',
  high: 'bg-orange-100 text-orange-800 border-orange-200',
  medium: 'bg-amber-100 text-amber-800 border-amber-200',
  low: 'bg-blue-100 text-blue-800 border-blue-200',
  info: 'bg-slate-100 text-slate-600 border-slate-200',
}

const TYPE_LABELS: Record<string, string> = {
  staleness_alert: 'Staleness',
  anomaly: 'Anomaly',
  tier_graduation: 'Graduation',
  conflict_review: 'Conflict',
  assessment_finding: 'Assessment',
  pipeline_failure: 'Pipeline',
  general: 'General',
}

function SeverityBadge({ severity }: { severity: DecisionSeverity }) {
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-xs font-semibold border ${SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.info}`}
    >
      {severity.toUpperCase()}
    </span>
  )
}

function TypePill({ type }: { type: string }) {
  return (
    <span className="inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200">
      {TYPE_LABELS[type] ?? type}
    </span>
  )
}

function formatAge(dateStr: string): string {
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  const diffMs = now - then
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60))

  if (diffDays > 1) return `${diffDays} days ago`
  if (diffDays === 1) return '1 day ago'
  if (diffHours > 1) return `${diffHours} hours ago`
  if (diffHours === 1) return '1 hour ago'
  return 'just now'
}

function DecisionCard({ decision }: { decision: PendingDecision }) {
  const isResolved = decision.status !== 'pending'
  const evidence = decision.evidence && Object.keys(decision.evidence).length > 0
    ? decision.evidence
    : null

  return (
    <div className={`rounded-lg border p-4 ${isResolved ? 'bg-slate-50 border-slate-200' : 'bg-white border-slate-200'}`}>
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <SeverityBadge severity={decision.severity} />
          <TypePill type={decision.decision_type} />
        </div>
        <span className="text-xs text-slate-400 whitespace-nowrap">
          {formatAge(decision.created_at)}
        </span>
      </div>

      <h3 className="text-sm font-semibold text-slate-800 mb-1">
        {decision.link ? (
          <a
            href={decision.link}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-civic-navy underline decoration-dotted"
          >
            {decision.title}
          </a>
        ) : (
          decision.title
        )}
      </h3>

      <p className="text-sm text-slate-600 mb-2 line-clamp-2">
        {decision.description}
      </p>

      <div className="flex items-center gap-3 text-xs text-slate-400">
        <span>Source: {decision.source}</span>
        <span className="font-mono">{decision.id.slice(0, 8)}</span>
      </div>

      {evidence && (
        <details className="mt-2">
          <summary className="text-xs text-slate-400 cursor-pointer hover:text-slate-600">
            Evidence
          </summary>
          <pre className="mt-1 text-xs bg-slate-50 rounded p-2 overflow-x-auto text-slate-600">
            {JSON.stringify(evidence, null, 2)}
          </pre>
        </details>
      )}

      {isResolved && (
        <div className="mt-2 pt-2 border-t border-slate-200">
          <div className="flex items-center gap-2 text-xs">
            <span className={`font-semibold ${
              decision.status === 'approved' ? 'text-green-700' :
              decision.status === 'rejected' ? 'text-red-700' :
              'text-amber-700'
            }`}>
              {decision.status.toUpperCase()}
            </span>
            {decision.resolved_at && (
              <span className="text-slate-400">{formatAge(decision.resolved_at)}</span>
            )}
          </div>
          {decision.resolution_note && (
            <p className="text-xs text-slate-500 mt-1">{decision.resolution_note}</p>
          )}
        </div>
      )}
    </div>
  )
}

function DecisionsDashboard() {
  const [data, setData] = useState<DecisionQueueResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showResolved, setShowResolved] = useState(false)

  useEffect(() => {
    fetch('/api/operator/decisions')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="text-center py-12 text-slate-500">
        Loading decision queue...
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-center py-12 text-red-600">
        Failed to load decisions: {error}
      </div>
    )
  }

  if (!data) return null

  const { summary, pending, recently_resolved } = data

  return (
    <div>
      {/* Header with severity counts */}
      <div className="flex items-center gap-4 mb-6 flex-wrap">
        <h2 className="text-lg font-bold text-slate-800">
          {summary.total_pending === 0
            ? 'No pending decisions'
            : `${summary.total_pending} pending decision${summary.total_pending !== 1 ? 's' : ''}`}
        </h2>
        {summary.total_pending > 0 && (
          <div className="flex gap-2">
            {(['critical', 'high', 'medium', 'low', 'info'] as DecisionSeverity[])
              .filter((s) => summary.counts[s] > 0)
              .map((s) => (
                <span key={s} className={`px-2 py-0.5 rounded text-xs font-medium border ${SEVERITY_STYLES[s]}`}>
                  {summary.counts[s]} {s}
                </span>
              ))}
          </div>
        )}
      </div>

      {/* Pending decisions */}
      {pending.length > 0 ? (
        <div className="space-y-3 mb-8">
          {pending.map((d) => (
            <DecisionCard key={d.id} decision={d} />
          ))}
        </div>
      ) : (
        <p className="text-slate-500 text-sm mb-8">
          All clear. No decisions awaiting operator judgment.
        </p>
      )}

      {/* Recently resolved */}
      {recently_resolved.length > 0 && (
        <div>
          <button
            onClick={() => setShowResolved(!showResolved)}
            className="text-sm font-medium text-slate-500 hover:text-slate-700 mb-3"
          >
            {showResolved ? 'Hide' : 'Show'} recently resolved ({recently_resolved.length})
          </button>

          {showResolved && (
            <div className="space-y-3">
              {recently_resolved.map((d) => (
                <DecisionCard key={d.id} decision={d} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function OperatorDecisionsPage() {
  return (
    <OperatorGate
      fallback={
        <div className="max-w-4xl mx-auto px-4 py-12 text-center text-slate-500">
          This page is only available in operator mode.
        </div>
      }
    >
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-slate-900">Operator Decision Queue</h1>
          <p className="text-sm text-slate-500 mt-1">
            Decisions requiring human judgment. Primary interface is Claude Code; this is the async read-only view.
          </p>
        </div>
        <DecisionsDashboard />
      </div>
    </OperatorGate>
  )
}
