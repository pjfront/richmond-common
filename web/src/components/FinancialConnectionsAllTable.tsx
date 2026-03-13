'use client'

import { useState, useMemo, useCallback, useEffect } from 'react'
import Link from 'next/link'
import VoteBadge from './VoteBadge'
import ConfidenceBadge from './ConfidenceBadge'
import CategoryBadge from './CategoryBadge'

/** Lightweight row returned by the API (no description/evidence) */
export interface ConnectionTableRow {
  id: string
  flag_type: string
  confidence: number
  meeting_id: string
  meeting_date: string
  agenda_item_id: string
  agenda_item_title: string
  agenda_item_number: string
  agenda_item_category: string | null
  vote_choice?: 'aye' | 'nay' | 'abstain' | 'absent' | null
  motion_result?: string | null
  is_unanimous?: boolean | null
  official_name: string
  official_slug: string
}

interface FlagDetails {
  description: string
  evidence: Record<string, unknown>[]
}

type SortKey = 'official_name' | 'meeting_date' | 'agenda_item_title' | 'flag_type' | 'confidence' | 'vote_choice'
type SortDir = 'asc' | 'desc'

function formatDate(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatFlagType(type: string): string {
  return type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

/** Build timestamp injected at compile time */
const BUILD_VERSION = `v${new Date().toISOString().slice(0, 10)}`

/**
 * Self-loading financial connections table.
 * Uses plain HTML table (no TanStack) for maximum performance.
 */
export default function FinancialConnectionsAllTable() {
  const [rows, setRows] = useState<ConnectionTableRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/flag-details?all=1')
      .then((res) => res.json())
      .then((data: ConnectionTableRow[]) => {
        setRows(data)
        setLoading(false)
      })
      .catch((err: Error) => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  if (loading) {
    return (
      <div className="py-8 text-center">
        <p className="text-sm text-slate-400 animate-pulse">Loading connections...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="py-8 text-center">
        <p className="text-sm text-red-500">Failed to load connections: {error}</p>
      </div>
    )
  }

  return <ConnectionsTable rows={rows} />
}

/** The actual table, rendered only after data is loaded */
function ConnectionsTable({ rows }: { rows: ConnectionTableRow[] }) {
  const [officialFilter, setOfficialFilter] = useState<string>('all')
  const [flagTypeFilter, setFlagTypeFilter] = useState<string>('all')
  const [voteFilter, setVoteFilter] = useState<string>('all')
  const [showAll, setShowAll] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('meeting_date')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())

  // Cache for on-demand detail fetches
  const [detailCache, setDetailCache] = useState<Record<string, FlagDetails>>({})
  const [loadingDetails, setLoadingDetails] = useState<Set<string>>(new Set())

  const fetchDetails = useCallback(async (flagId: string) => {
    if (detailCache[flagId] || loadingDetails.has(flagId)) return
    setLoadingDetails((prev) => new Set(prev).add(flagId))
    try {
      const res = await fetch(`/api/flag-details?id=${flagId}`)
      if (res.ok) {
        const data: FlagDetails = await res.json()
        setDetailCache((prev) => ({ ...prev, [flagId]: data }))
      }
    } finally {
      setLoadingDetails((prev) => {
        const next = new Set(prev)
        next.delete(flagId)
        return next
      })
    }
  }, [detailCache, loadingDetails])

  const officials = useMemo(() => {
    const names = new Map<string, string>()
    for (const r of rows) names.set(r.official_slug, r.official_name)
    return Array.from(names.entries()).sort(([, a], [, b]) => a.localeCompare(b))
  }, [rows])

  const flagTypes = useMemo(() => {
    const types = new Set<string>()
    for (const r of rows) types.add(r.flag_type)
    return Array.from(types).sort()
  }, [rows])

  const filtered = useMemo(() => {
    return rows.filter((r) => {
      if (officialFilter !== 'all' && r.official_slug !== officialFilter) return false
      if (flagTypeFilter !== 'all' && r.flag_type !== flagTypeFilter) return false
      if (voteFilter !== 'all') {
        if (voteFilter === 'none' && r.vote_choice !== null) return false
        if (voteFilter !== 'none' && r.vote_choice !== voteFilter) return false
      }
      return true
    })
  }, [rows, officialFilter, flagTypeFilter, voteFilter])

  const sorted = useMemo(() => {
    const arr = [...filtered]
    arr.sort((a, b) => {
      const valA = a[sortKey] ?? ''
      const valB = b[sortKey] ?? ''
      if (typeof valA === 'number' && typeof valB === 'number') {
        return sortDir === 'asc' ? valA - valB : valB - valA
      }
      const strA = String(valA)
      const strB = String(valB)
      const cmp = strA.localeCompare(strB)
      return sortDir === 'asc' ? cmp : -cmp
    })
    return arr
  }, [filtered, sortKey, sortDir])

  const displayed = showAll ? sorted : sorted.slice(0, 30)

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  function toggleExpand(id: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
        fetchDetails(id)
      }
      return next
    })
  }

  function SortIcon({ col }: { col: SortKey }) {
    if (sortKey !== col) return <span className="text-slate-300 ml-0.5">↕</span>
    return <span className="ml-0.5">{sortDir === 'asc' ? '↑' : '↓'}</span>
  }

  return (
    <div>
      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-3">
        <select
          value={officialFilter}
          onChange={(e) => setOfficialFilter(e.target.value)}
          className="text-sm border border-slate-200 rounded px-2 py-1"
        >
          <option value="all">All officials</option>
          {officials.map(([slug, name]) => (
            <option key={slug} value={slug}>{name}</option>
          ))}
        </select>
        <select
          value={flagTypeFilter}
          onChange={(e) => setFlagTypeFilter(e.target.value)}
          className="text-sm border border-slate-200 rounded px-2 py-1"
        >
          <option value="all">All types</option>
          {flagTypes.map((t) => (
            <option key={t} value={t}>{formatFlagType(t)}</option>
          ))}
        </select>
        <select
          value={voteFilter}
          onChange={(e) => setVoteFilter(e.target.value)}
          className="text-sm border border-slate-200 rounded px-2 py-1"
        >
          <option value="all">All votes</option>
          <option value="aye">Aye</option>
          <option value="nay">Nay</option>
          <option value="abstain">Abstain</option>
          <option value="absent">Absent</option>
          <option value="none">No vote recorded</option>
        </select>
        <span className="text-xs text-slate-400 self-center">
          {displayed.length} of {rows.length}
          {filtered.length < rows.length && ` (${filtered.length} match filters)`}
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto border border-slate-200 rounded-lg">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200">
              <th className="px-3 py-2 w-8" />
              <th className="px-3 py-2 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                <button onClick={() => toggleSort('official_name')} className="cursor-pointer select-none hover:text-civic-navy">
                  Official <SortIcon col="official_name" />
                </button>
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                <button onClick={() => toggleSort('meeting_date')} className="cursor-pointer select-none hover:text-civic-navy">
                  Date <SortIcon col="meeting_date" />
                </button>
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                <button onClick={() => toggleSort('agenda_item_title')} className="cursor-pointer select-none hover:text-civic-navy">
                  Agenda Item <SortIcon col="agenda_item_title" />
                </button>
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                <button onClick={() => toggleSort('flag_type')} className="cursor-pointer select-none hover:text-civic-navy">
                  Type <SortIcon col="flag_type" />
                </button>
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                <button onClick={() => toggleSort('confidence')} className="cursor-pointer select-none hover:text-civic-navy">
                  Confidence <SortIcon col="confidence" />
                </button>
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                <button onClick={() => toggleSort('vote_choice')} className="cursor-pointer select-none hover:text-civic-navy">
                  Vote <SortIcon col="vote_choice" />
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            {displayed.map((row) => {
              const isExpanded = expandedIds.has(row.id)
              return (
                <TableRow
                  key={row.id}
                  row={row}
                  isExpanded={isExpanded}
                  onToggle={() => toggleExpand(row.id)}
                  details={detailCache[row.id]}
                  loadingDetail={loadingDetails.has(row.id)}
                />
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Show all toggle */}
      {filtered.length > 30 && !showAll && (
        <button
          onClick={() => setShowAll(true)}
          className="mt-2 text-sm text-civic-navy-light hover:text-civic-navy"
        >
          Show all {filtered.length} connections
        </button>
      )}

      {/* Version indicator */}
      <p className="mt-3 text-xs text-slate-300 text-left">{BUILD_VERSION}</p>
    </div>
  )
}

/** Individual table row + expandable detail */
function TableRow({
  row,
  isExpanded,
  onToggle,
  details,
  loadingDetail,
}: {
  row: ConnectionTableRow
  isExpanded: boolean
  onToggle: () => void
  details?: FlagDetails
  loadingDetail: boolean
}) {
  return (
    <>
      <tr
        className={`border-b border-slate-100 hover:bg-slate-50/50 cursor-pointer ${isExpanded ? 'bg-slate-50/50' : ''}`}
        onClick={onToggle}
      >
        <td className="px-3 py-2">
          <span className="text-slate-400 hover:text-civic-navy px-1">
            {isExpanded ? '▾' : '▸'}
          </span>
        </td>
        <td className="px-3 py-2">
          <Link
            href={`/council/${row.official_slug}`}
            className="text-civic-navy-light hover:text-civic-navy font-medium whitespace-nowrap"
            onClick={(e) => e.stopPropagation()}
          >
            {row.official_name}
          </Link>
        </td>
        <td className="px-3 py-2">
          <Link
            href={`/meetings/${row.meeting_id}`}
            className="text-civic-navy-light hover:text-civic-navy whitespace-nowrap"
            onClick={(e) => e.stopPropagation()}
          >
            {formatDate(row.meeting_date)}
          </Link>
        </td>
        <td className="px-3 py-2">
          <div className="min-w-[180px]">
            <p className="text-sm text-slate-800 line-clamp-2">
              <span className="text-slate-400 mr-1">{row.agenda_item_number}.</span>
              {row.agenda_item_title}
            </p>
            <CategoryBadge category={row.agenda_item_category} />
          </div>
        </td>
        <td className="px-3 py-2">
          <span className="text-xs text-slate-600 whitespace-nowrap">
            {formatFlagType(row.flag_type)}
          </span>
        </td>
        <td className="px-3 py-2">
          <ConfidenceBadge confidence={row.confidence} />
        </td>
        <td className="px-3 py-2">
          {row.vote_choice ? (
            <VoteBadge choice={row.vote_choice} />
          ) : (
            <span className="text-xs text-slate-400">No vote</span>
          )}
        </td>
      </tr>
      {isExpanded && (
        <tr className="border-b border-slate-100 bg-slate-50/80">
          <td colSpan={7} className="px-4 py-3">
            <ExpandedDetails
              flagId={row.id}
              details={details}
              loading={loadingDetail}
            />
          </td>
        </tr>
      )}
    </>
  )
}

/** Expanded row detail, loads on-demand */
function ExpandedDetails({
  flagId,
  details,
  loading,
}: {
  flagId: string
  details?: FlagDetails
  loading: boolean
}) {
  if (loading || !details) {
    return (
      <p className="text-sm text-slate-400 animate-pulse">
        Loading details...
      </p>
    )
  }

  return (
    <>
      <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-line">
        {details.description}
      </p>
      {details.evidence && details.evidence.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {details.evidence.map((e, i) => (
            <span key={`${flagId}-ev-${i}`} className="text-xs text-slate-500 bg-slate-100 rounded px-2 py-0.5">
              {(e as Record<string, string>).text ?? JSON.stringify(e)}
            </span>
          ))}
        </div>
      )}
    </>
  )
}
