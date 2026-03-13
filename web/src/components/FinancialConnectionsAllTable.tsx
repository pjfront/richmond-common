'use client'

import { useState, useMemo, useCallback, Fragment } from 'react'
import Link from 'next/link'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getExpandedRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
  type ExpandedState,
} from '@tanstack/react-table'
import SortableHeader from './SortableHeader'
import VoteBadge from './VoteBadge'
import ConfidenceBadge from './ConfidenceBadge'
import CategoryBadge from './CategoryBadge'

/** Lightweight row: no description/evidence (fetched on expand) */
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
  vote_choice: 'aye' | 'nay' | 'abstain' | 'absent' | null
  motion_result: string | null
  is_unanimous: boolean | null
  official_name: string
  official_slug: string
}

interface FlagDetails {
  description: string
  evidence: Record<string, unknown>[]
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatFlagType(type: string): string {
  return type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

const columnHelper = createColumnHelper<ConnectionTableRow>()

export default function FinancialConnectionsAllTable({
  rows,
}: {
  rows: ConnectionTableRow[]
}) {
  const [officialFilter, setOfficialFilter] = useState<string>('all')
  const [flagTypeFilter, setFlagTypeFilter] = useState<string>('all')
  const [voteFilter, setVoteFilter] = useState<string>('all')
  const [showAll, setShowAll] = useState(false)
  const [sorting, setSorting] = useState<SortingState>([])
  const [expanded, setExpanded] = useState<ExpandedState>({})

  // Cache for on-demand detail fetches (description + evidence)
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
    const names = new Map<string, string>() // slug -> name
    for (const r of rows) names.set(r.official_slug, r.official_name)
    return Array.from(names.entries()).sort(([, a], [, b]) => a.localeCompare(b))
  }, [rows])

  const flagTypes = useMemo(() => {
    const types = new Set<string>()
    for (const r of rows) types.add(r.flag_type)
    return Array.from(types).sort()
  }, [rows])

  // Progressive rendering: show 30 initially, add 50 more per batch to avoid
  // freezing Chrome when "Show all" is clicked with 300+ rows
  const [visibleCount, setVisibleCount] = useState(30)

  // Reset visible count when filters change
  const filterKey = `${officialFilter}|${flagTypeFilter}|${voteFilter}`
  const [prevFilterKey, setPrevFilterKey] = useState(filterKey)
  if (filterKey !== prevFilterKey) {
    setPrevFilterKey(filterKey)
    setVisibleCount(30)
    setShowAll(false)
  }

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

  const displayed = filtered.slice(0, showAll ? visibleCount : 30)

  // When showAll is toggled or visibleCount increases, schedule next batch
  const hasMore = showAll && visibleCount < filtered.length
  if (hasMore) {
    // Use requestIdleCallback (or setTimeout fallback) to render next batch
    // without blocking the main thread
    if (typeof requestIdleCallback !== 'undefined') {
      requestIdleCallback(() => setVisibleCount((c) => Math.min(c + 50, filtered.length)))
    } else {
      setTimeout(() => setVisibleCount((c) => Math.min(c + 50, filtered.length)), 16)
    }
  }

  const columns = useMemo(
    () => [
      columnHelper.display({
        id: 'expand',
        header: () => null,
        cell: ({ row }) => (
          <button
            onClick={(e) => { e.stopPropagation(); row.toggleExpanded() }}
            className="text-slate-400 hover:text-civic-navy px-1"
            aria-label={row.getIsExpanded() ? 'Collapse details' : 'Expand details'}
          >
            {row.getIsExpanded() ? '▾' : '▸'}
          </button>
        ),
        size: 30,
      }),
      columnHelper.accessor('official_name', {
        header: ({ column }) => <SortableHeader column={column} label="Official" />,
        cell: (info) => (
          <Link
            href={`/council/${info.row.original.official_slug}`}
            className="text-civic-navy-light hover:text-civic-navy font-medium whitespace-nowrap"
            onClick={(e) => e.stopPropagation()}
          >
            {info.getValue()}
          </Link>
        ),
      }),
      columnHelper.accessor('meeting_date', {
        header: ({ column }) => <SortableHeader column={column} label="Date" />,
        cell: (info) => (
          <Link
            href={`/meetings/${info.row.original.meeting_id}`}
            className="text-civic-navy-light hover:text-civic-navy whitespace-nowrap"
            onClick={(e) => e.stopPropagation()}
          >
            {formatDate(info.getValue())}
          </Link>
        ),
        sortingFn: 'alphanumeric',
      }),
      columnHelper.accessor('agenda_item_title', {
        header: ({ column }) => <SortableHeader column={column} label="Agenda Item" />,
        cell: (info) => (
          <div className="min-w-[180px]">
            <p className="text-sm text-slate-800 line-clamp-2">
              <span className="text-slate-400 mr-1">{info.row.original.agenda_item_number}.</span>
              {info.getValue()}
            </p>
            <CategoryBadge category={info.row.original.agenda_item_category} />
          </div>
        ),
      }),
      columnHelper.accessor('flag_type', {
        header: ({ column }) => <SortableHeader column={column} label="Type" />,
        cell: (info) => (
          <span className="text-xs text-slate-600 whitespace-nowrap">
            {formatFlagType(info.getValue())}
          </span>
        ),
      }),
      columnHelper.accessor('confidence', {
        header: ({ column }) => <SortableHeader column={column} label="Confidence" />,
        cell: (info) => <ConfidenceBadge confidence={info.getValue()} />,
        sortingFn: 'basic',
      }),
      columnHelper.accessor('vote_choice', {
        header: ({ column }) => <SortableHeader column={column} label="Vote" />,
        cell: (info) => {
          const choice = info.getValue()
          if (!choice) return <span className="text-xs text-slate-400">No vote</span>
          return <VoteBadge choice={choice} />
        },
      }),
    ],
    []
  )

  const table = useReactTable({
    data: displayed,
    columns,
    state: { sorting, expanded },
    onSortingChange: setSorting,
    onExpandedChange: setExpanded,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
  })

  const handleRowClick = (row: ReturnType<typeof table.getRowModel>['rows'][number]) => {
    row.toggleExpanded()
    // Fetch details on expand if not already cached
    if (!row.getIsExpanded()) {
      fetchDetails(row.original.id)
    }
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
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="bg-slate-50 border-b border-slate-200">
                {headerGroup.headers.map((header) => (
                  <th key={header.id} className="px-3 py-2 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                    {flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <Fragment key={row.id}>
                <tr
                  className={`border-b border-slate-100 hover:bg-slate-50/50 cursor-pointer ${row.getIsExpanded() ? 'bg-slate-50/50' : ''}`}
                  onClick={() => handleRowClick(row)}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-3 py-2">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
                {row.getIsExpanded() && (
                  <tr className="border-b border-slate-100 bg-slate-50/80">
                    <td colSpan={columns.length} className="px-4 py-3">
                      <ExpandedDetails
                        flagId={row.original.id}
                        details={detailCache[row.original.id]}
                        loading={loadingDetails.has(row.original.id)}
                      />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {/* Show all toggle */}
      {filtered.length > 30 && !showAll && (
        <button
          onClick={() => { setShowAll(true); setVisibleCount(80) }}
          className="mt-2 text-sm text-civic-navy-light hover:text-civic-navy"
        >
          Show all {filtered.length} connections
        </button>
      )}
      {hasMore && (
        <p className="mt-2 text-xs text-slate-400">
          Loading rows... ({displayed.length} of {filtered.length})
        </p>
      )}
    </div>
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
