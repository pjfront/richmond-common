'use client'

import { useState, useMemo } from 'react'
import type { NextRequestRequest, PublicRecordsStats } from '@/lib/types'
import ComplianceStats from './ComplianceStats'

const CLOSED_STATUSES = new Set(['closed', 'completed'])
const PAGE_SIZE = 50

function statusBadge(status: string) {
  const lower = (status || '').toLowerCase()
  if (CLOSED_STATUSES.has(lower)) {
    return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700">Closed</span>
  }
  if (lower === 'open' || lower === 'due soon') {
    return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700">{status}</span>
  }
  return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600">{status}</span>
}

function responseNarrative(request: NextRequestRequest): string {
  if (!CLOSED_STATUSES.has((request.status || '').trim().toLowerCase())) {
    return `Portal status: ${request.status || 'Unknown'}`
  }
  const days = request.days_to_close
  if (typeof days !== 'number' || !Number.isInteger(days) || days < 0) return 'Marked closed; closure duration unavailable'
  return `Marked closed ${days} day${days !== 1 ? 's' : ''} after submission`
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return ''
  const d = new Date(dateStr.slice(0, 10) + 'T00:00:00')
  if (!Number.isFinite(d.getTime())) return ''
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

interface Props {
  requests: NextRequestRequest[]
  stats: PublicRecordsStats
}

export default function PublicRecordsClient({ requests, stats }: Props) {
  const [selectedDepartment, setSelectedDepartment] = useState<string | null>(null)
  const [selectedStatus, setSelectedStatus] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())

  // Compute department counts for the dropdown
  const departmentCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const r of requests) {
      const dept = r.department || 'Unknown'
      counts.set(dept, (counts.get(dept) ?? 0) + 1)
    }
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
  }, [requests])

  // Compute status counts
  const statusCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const r of requests) {
      const status = r.status || 'Unknown'
      counts.set(status, (counts.get(status) ?? 0) + 1)
    }
    return counts
  }, [requests])

  // Filter
  const filtered = useMemo(() => {
    let result = requests
    if (selectedDepartment) {
      result = result.filter((r) => (r.department || 'Unknown') === selectedDepartment)
    }
    if (selectedStatus) {
      result = result.filter((r) => r.status === selectedStatus)
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      result = result.filter((r) =>
        (r.request_number || '').toLowerCase().includes(q) ||
        (r.department || '').toLowerCase().includes(q)
      )
    }
    return result
  }, [requests, selectedDepartment, selectedStatus, searchQuery])

  const visible = filtered.slice(0, visibleCount)
  const hasMore = visibleCount < filtered.length

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const clearFilters = () => {
    setSelectedDepartment(null)
    setSelectedStatus(null)
    setSearchQuery('')
    setVisibleCount(PAGE_SIZE)
  }

  const hasActiveFilters = selectedDepartment || selectedStatus || searchQuery.trim()

  return (
    <div>
      <div className="mb-8"><ComplianceStats stats={stats} /></div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <select
          aria-label="Filter by department listing"
          value={selectedDepartment ?? ''}
          onChange={(e) => {
            setSelectedDepartment(e.target.value || null)
            setVisibleCount(PAGE_SIZE)
          }}
          className="w-full min-w-0 max-w-full truncate rounded-md border border-slate-300 px-3 py-1.5 text-sm bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-civic-navy/20"
        >
          <option value="">All departments</option>
          {departmentCounts.map(([dept, count]) => (
            <option key={dept} value={dept}>
              {dept} ({count})
            </option>
          ))}
        </select>

        <div className="flex flex-wrap gap-1.5">
          {Array.from(statusCounts.entries())
            .sort((a, b) => b[1] - a[1])
            .map(([status, count]) => (
              <button
                key={status}
                onClick={() => {
                  setSelectedStatus(selectedStatus === status ? null : status)
                  setVisibleCount(PAGE_SIZE)
                }}
                className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                  selectedStatus === status
                    ? 'bg-civic-navy text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {status} ({count})
              </button>
            ))}
        </div>

        <input
          type="text"
          aria-label="Search request number or department"
          placeholder="Request number or department"
          value={searchQuery}
          onChange={(e) => {
            setSearchQuery(e.target.value)
            setVisibleCount(PAGE_SIZE)
          }}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm bg-white text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-civic-navy/20 w-48"
        />

        {hasActiveFilters && (
          <button
            onClick={clearFilters}
            className="text-xs text-slate-500 hover:text-slate-700 underline"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Result count */}
      <p className="text-sm text-slate-500 mb-4">
        {hasActiveFilters
          ? `Showing ${filtered.length.toLocaleString()} of ${requests.length.toLocaleString()} requests`
          : `${requests.length.toLocaleString()} indexed public records requests`}
      </p>

      {/* Request cards */}
      <div className="space-y-2">
        {visible.map((r) => {
          const isExpanded = expandedIds.has(r.id)
          const narrative = responseNarrative(r)

          return (
            <div
              key={r.id}
              className="bg-white rounded-lg border border-slate-200 hover:border-slate-300 transition-colors"
            >
              {/* Header row — always visible */}
              <button
                onClick={() => toggleExpand(r.id)}
                className="w-full text-left px-4 py-3 flex items-start justify-between gap-3"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-xs font-mono text-slate-400">#{r.request_number}</span>
                    {r.department && (
                      <span className="px-2 py-0.5 rounded text-xs bg-civic-navy/10 text-civic-navy font-medium truncate max-w-[200px]">
                        {r.department}
                      </span>
                    )}
                    {statusBadge(r.status)}
                  </div>
                  <p className="text-sm text-slate-700 line-clamp-1">
                    {`Request #${r.request_number}`}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0 text-xs text-slate-400">
                  <span>{formatDate(r.submitted_date)}</span>
                  <span className="text-slate-300">{isExpanded ? '−' : '+'}</span>
                </div>
              </button>

              {/* Expanded detail */}
              {isExpanded && (
                <div className="px-4 pb-4 border-t border-slate-100 pt-3">
                  <p className="text-sm text-slate-700 mb-3">Read the request and correspondence on the linked source portal.</p>

                  {/* Timeline */}
                  <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-500 mb-3">
                    {r.submitted_date && (
                      <span>Submitted: {formatDate(r.submitted_date)}</span>
                    )}
                    {r.due_date && (
                      <span>Portal due date: {formatDate(r.due_date)}</span>
                    )}
                    {r.closed_date && (
                      <span>Closed: {formatDate(r.closed_date)}</span>
                    )}
                    {r.document_count != null && r.document_count > 0 && (
                      <span>{r.document_count} document{r.document_count !== 1 ? 's' : ''}</span>
                    )}
                  </div>

                  {/* Response narrative */}
                  {narrative && (
                    <p className="text-sm font-medium text-slate-700 mb-3">
                      {narrative}
                    </p>
                  )}

                  {formatDate(r.updated_at) && <p className="text-xs text-slate-500 mb-3">Record updated: {formatDate(r.updated_at)}</p>}
                  {/* Portal link */}
                  {r.portal_url && (
                    <a
                      href={r.portal_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-sm text-civic-navy hover:underline"
                    >
                      View full request on NextRequest
                      <span aria-hidden="true">&rarr;</span>
                    </a>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Show more */}
      {hasMore && (
        <div className="mt-4 text-center">
          <button
            onClick={() => setVisibleCount((prev) => prev + PAGE_SIZE)}
            className="px-6 py-2 rounded-md border border-slate-300 text-sm text-slate-600 hover:bg-slate-50 transition-colors"
          >
            Show more ({Math.min(PAGE_SIZE, filtered.length - visibleCount)} more of {filtered.length.toLocaleString()})
          </button>
        </div>
      )}

      {filtered.length === 0 && (
        <p className="text-center text-slate-500 py-8">
          No requests match your filters.
        </p>
      )}
    </div>
  )
}
