'use client'

import { useState, useMemo } from 'react'
import Link from 'next/link'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from '@tanstack/react-table'
import SortableHeader from './SortableHeader'
import VoteBadge from './VoteBadge'
import ConfidenceBadge from './ConfidenceBadge'
import CategoryBadge from './CategoryBadge'
import type { FinancialConnectionFlag } from '@/lib/types'

function formatDate(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatFlagType(type: string): string {
  return type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

const columnHelper = createColumnHelper<FinancialConnectionFlag>()

export default function FinancialConnectionsTable({
  flags,
}: {
  flags: FinancialConnectionFlag[]
}) {
  const [flagTypeFilter, setFlagTypeFilter] = useState<string>('all')
  const [voteFilter, setVoteFilter] = useState<string>('all')
  const [showAll, setShowAll] = useState(false)
  const [sorting, setSorting] = useState<SortingState>([])

  const flagTypes = useMemo(() => {
    const types = new Set<string>()
    for (const f of flags) types.add(f.flag_type)
    return Array.from(types).sort()
  }, [flags])

  const filtered = useMemo(() => {
    return flags.filter((f) => {
      if (flagTypeFilter !== 'all' && f.flag_type !== flagTypeFilter) return false
      if (voteFilter !== 'all') {
        if (voteFilter === 'none' && f.vote_choice !== null) return false
        if (voteFilter !== 'none' && f.vote_choice !== voteFilter) return false
      }
      return true
    })
  }, [flags, flagTypeFilter, voteFilter])

  const displayed = showAll ? filtered : filtered.slice(0, 20)

  const columns = useMemo(
    () => [
      columnHelper.accessor('meeting_date', {
        header: ({ column }) => <SortableHeader column={column} label="Date" />,
        cell: (info) => (
          <Link
            href={`/meetings/${info.row.original.meeting_id}`}
            className="text-civic-navy-light hover:text-civic-navy whitespace-nowrap"
          >
            {formatDate(info.getValue())}
          </Link>
        ),
        sortingFn: 'alphanumeric',
      }),
      columnHelper.accessor('agenda_item_title', {
        header: ({ column }) => <SortableHeader column={column} label="Agenda Item" />,
        cell: (info) => (
          <div className="min-w-[200px]">
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
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  if (flags.length === 0) {
    return (
      <div className="bg-green-50 border border-green-200 rounded-lg p-4">
        <p className="text-sm text-green-700">
          No financial connections have been identified for this official.
        </p>
      </div>
    )
  }

  return (
    <div>
      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-3">
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
          {filtered.length} of {flags.length} shown
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
              <tr key={row.id} className="border-b border-slate-100 hover:bg-slate-50/50">
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-3 py-2">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Show all toggle */}
      {filtered.length > 20 && !showAll && (
        <button
          onClick={() => setShowAll(true)}
          className="mt-2 text-sm text-civic-navy-light hover:text-civic-navy"
        >
          Show all {filtered.length} connections
        </button>
      )}
    </div>
  )
}
