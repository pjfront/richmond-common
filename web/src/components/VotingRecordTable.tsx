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

interface VoteRecord {
  id: string
  vote_choice: string
  meeting_id: string
  agenda_item_id?: string
  meeting_date: string
  meeting_type: string
  item_number: string
  item_title: string
  category: string | null
  topic_label?: string | null
  motion_result: string
  vote_tally?: string | null
  is_consent_calendar: boolean
}

/** Returns true if this vote was part of a split (non-unanimous) decision */
function isSplitVote(record: VoteRecord): boolean {
  // If we have a vote_tally like "5-2" or "Ayes (5): ... Noes (2): ...", parse it
  if (record.vote_tally) {
    // Check for "N-N" pattern (e.g., "5-2", "4-3")
    const dashMatch = record.vote_tally.match(/^(\d+)\s*-\s*(\d+)/)
    if (dashMatch) {
      const [, ayes, noes] = dashMatch
      return parseInt(ayes) > 0 && parseInt(noes) > 0
    }
    // Check for "Noes (N)" or "Nays (N)" pattern with N > 0
    const noesMatch = record.vote_tally.match(/No[ea]s?\s*\((\d+)\)/i)
    if (noesMatch && parseInt(noesMatch[1]) > 0) return true
    // Check for "Abstentions (N)" pattern with N > 0
    const abstainMatch = record.vote_tally.match(/Abstentions?\s*\((\d+)\)/i)
    if (abstainMatch && parseInt(abstainMatch[1]) > 0) return true
  }
  // Fallback: if result contains numbers suggesting a split
  if (record.motion_result) {
    const resultDash = record.motion_result.match(/^(\d+)\s*-\s*(\d+)/)
    if (resultDash) {
      return parseInt(resultDash[1]) > 0 && parseInt(resultDash[2]) > 0
    }
  }
  return false
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatCategory(cat: string): string {
  return cat.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

const columnHelper = createColumnHelper<VoteRecord>()

export default function VotingRecordTable({ votes }: { votes: VoteRecord[] }) {
  const [categoryFilter, setCategoryFilter] = useState<string>('all')
  const [choiceFilter, setChoiceFilter] = useState<string>('all')
  const [hideConsent, setHideConsent] = useState(false)
  const [splitOnly, setSplitOnly] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const [sorting, setSorting] = useState<SortingState>([])

  const categories = useMemo(() => {
    const cats = new Set<string>()
    for (const v of votes) {
      if (v.category) cats.add(v.category)
    }
    return Array.from(cats).sort()
  }, [votes])

  const filtered = useMemo(() => {
    return votes.filter((v) => {
      if (categoryFilter !== 'all' && v.category !== categoryFilter) return false
      if (choiceFilter !== 'all' && v.vote_choice.toLowerCase() !== choiceFilter) return false
      if (hideConsent && v.is_consent_calendar) return false
      if (splitOnly && !isSplitVote(v)) return false
      return true
    })
  }, [votes, categoryFilter, choiceFilter, hideConsent, splitOnly])

  const splitCount = useMemo(() => votes.filter(isSplitVote).length, [votes])

  const columns = useMemo(() => [
    columnHelper.accessor('meeting_date', {
      header: ({ column }) => <SortableHeader column={column} label="Date" />,
      cell: (info) => (
        <Link
          href={`/meetings/${info.row.original.meeting_id}`}
          className="text-slate-500 hover:text-civic-navy-light whitespace-nowrap"
        >
          {formatDate(info.getValue())}
        </Link>
      ),
      sortingFn: 'text',
    }),
    columnHelper.display({
      id: 'item',
      header: 'Item',
      cell: (info) => {
        const row = info.row.original
        return (
          <Link
            href={`/meetings/${row.meeting_id}`}
            className="block text-slate-900 hover:text-civic-navy-light"
          >
            <span className="text-xs font-mono text-slate-400 mr-1">
              {row.item_number}
            </span>
            <span className="line-clamp-1">{row.item_title}</span>
          </Link>
        )
      },
    }),
    columnHelper.display({
      id: 'topic',
      header: 'Topic',
      cell: (info) => {
        const row = info.row.original
        const label = row.topic_label || (row.category ? formatCategory(row.category) : null)
        return label ? (
          <span className="text-xs text-slate-500">{label}</span>
        ) : '\u2014'
      },
      meta: { className: 'hidden md:table-cell' },
    }),
    columnHelper.accessor('vote_choice', {
      header: ({ column }) => <SortableHeader column={column} label="Vote" />,
      cell: (info) => <VoteBadge choice={info.getValue()} />,
    }),
    columnHelper.accessor('motion_result', {
      header: ({ column }) => (
        <SortableHeader column={column} label="Result" className="hidden sm:table-cell" />
      ),
      cell: (info) => (
        <span className="text-xs text-slate-500 capitalize">{info.getValue()}</span>
      ),
      meta: { className: 'hidden sm:table-cell' },
    }),
  ], [])

  const table = useReactTable({
    data: filtered,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  if (votes.length === 0) {
    return <p className="text-sm text-slate-500 italic">No voting record available.</p>
  }

  const allRows = table.getRowModel().rows
  const visibleRows = showAll ? allRows : allRows.slice(0, 25)

  return (
    <div>
      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4">
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="text-sm border border-slate-200 rounded px-2 py-1 text-slate-700"
        >
          <option value="all">All Categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {formatCategory(c)}
            </option>
          ))}
        </select>
        <select
          value={choiceFilter}
          onChange={(e) => setChoiceFilter(e.target.value)}
          className="text-sm border border-slate-200 rounded px-2 py-1 text-slate-700"
        >
          <option value="all">All Votes</option>
          <option value="aye">Aye</option>
          <option value="nay">Nay</option>
          <option value="abstain">Abstain</option>
          <option value="absent">Absent</option>
        </select>
        <label className="flex items-center gap-1.5 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={hideConsent}
            onChange={(e) => setHideConsent(e.target.checked)}
            className="rounded"
          />
          Hide consent calendar
        </label>
        {splitCount > 0 && (
          <label className="flex items-center gap-1.5 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={splitOnly}
              onChange={(e) => setSplitOnly(e.target.checked)}
              className="rounded"
            />
            Split votes only
            <span className="text-xs text-civic-amber">({splitCount})</span>
          </label>
        )}
        <span className="text-xs text-slate-400 self-center">
          {filtered.length} of {votes.length} votes
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="border-b border-slate-200 text-left">
                {headerGroup.headers.map((header) => {
                  const meta = header.column.columnDef.meta as { className?: string } | undefined
                  return (
                    <th key={header.id} className={`py-2 pr-3 font-medium text-slate-600 ${meta?.className ?? ''}`}>
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.header, header.getContext())}
                    </th>
                  )
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {visibleRows.map((row) => (
              <tr key={row.id} className="border-b border-slate-100">
                {row.getVisibleCells().map((cell) => {
                  const meta = cell.column.columnDef.meta as { className?: string } | undefined
                  return (
                    <td key={cell.id} className={`py-2 pr-3 ${meta?.className ?? ''}`}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!showAll && filtered.length > 25 && (
        <button
          onClick={() => setShowAll(true)}
          className="mt-2 text-sm text-civic-navy-light hover:text-civic-navy"
        >
          Show all {filtered.length} votes
        </button>
      )}
    </div>
  )
}
