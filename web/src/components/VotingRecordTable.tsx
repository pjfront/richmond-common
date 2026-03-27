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
import CivicTerm from './CivicTerm'

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
  public_comment_count?: number
  motion_result: string
  vote_tally?: string | null
  has_nay_votes?: boolean
  is_consent_calendar: boolean
  // Set by groupByItem() when collapsing multiple motions
  motion_count?: number
  all_choices?: string[]
}

/** Returns true if this vote was part of a split (non-unanimous) decision */
function isSplitVote(record: VoteRecord): boolean {
  // Use actual vote records when available (avoids vote_tally text parsing bugs
  // where absent/abstain members were incorrectly counted as nay votes)
  if (record.has_nay_votes !== undefined) {
    return record.has_nay_votes
  }
  // Fallback to vote_tally text parsing for records without has_nay_votes
  if (record.vote_tally) {
    const dashMatch = record.vote_tally.match(/^(\d+)\s*-\s*(\d+)/)
    if (dashMatch) {
      return parseInt(dashMatch[1]) > 0 && parseInt(dashMatch[2]) > 0
    }
    const noesMatch = record.vote_tally.match(/No[ea]s?\s*\((\d+)\)/i)
    if (noesMatch && parseInt(noesMatch[1]) > 0) return true
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

/** Collapse multiple motions on the same agenda item into one row */
function groupByItem(votes: VoteRecord[]): VoteRecord[] {
  const groups = new Map<string, VoteRecord[]>()
  for (const v of votes) {
    const key = v.agenda_item_id ?? v.id
    const existing = groups.get(key)
    if (existing) existing.push(v)
    else groups.set(key, [v])
  }
  return Array.from(groups.values()).map((motions) => {
    const first = motions[0]
    if (motions.length === 1) return first
    const choices = [...new Set(motions.map((m) => m.vote_choice.toLowerCase()))]
    return {
      ...first,
      motion_count: motions.length,
      has_nay_votes: motions.some(isSplitVote),
      ...(choices.length > 1 ? { all_choices: motions.map((m) => m.vote_choice) } : {}),
    }
  })
}

const columnHelper = createColumnHelper<VoteRecord>()

export default function VotingRecordTable({ votes }: { votes: VoteRecord[] }) {
  const [topicFilter, setTopicFilter] = useState<string>('all')
  const [choiceFilter, setChoiceFilter] = useState<string>('all')
  const [hideConsent, setHideConsent] = useState(false)
  const [splitOnly, setSplitOnly] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'meeting_date', desc: true },
  ])

  // Collapse multiple motions on the same agenda item into one row
  const grouped = useMemo(() => groupByItem(votes), [votes])

  // Build topic labels for filter (prefer topic_label, fall back to category)
  const topics = useMemo(() => {
    const labels = new Set<string>()
    for (const v of grouped) {
      const label = v.topic_label || (v.category ? formatCategory(v.category) : null)
      if (label) labels.add(label)
    }
    return Array.from(labels).sort()
  }, [grouped])

  const filtered = useMemo(() => {
    return grouped.filter((v) => {
      if (topicFilter !== 'all') {
        const label = v.topic_label || (v.category ? formatCategory(v.category) : null)
        if (label !== topicFilter) return false
      }
      if (choiceFilter !== 'all' && v.vote_choice.toLowerCase() !== choiceFilter) return false
      if (hideConsent && v.is_consent_calendar) return false
      if (splitOnly && !v.has_nay_votes) return false
      return true
    })
  }, [grouped, topicFilter, choiceFilter, hideConsent, splitOnly])

  const splitCount = useMemo(() => grouped.filter((v) => v.has_nay_votes).length, [grouped])

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
            <span className="line-clamp-1">
              {row.item_title}
              {(row.motion_count ?? 1) > 1 && (
                <span className="text-xs text-slate-400 ml-1">
                  ({row.motion_count} motions)
                </span>
              )}
            </span>
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
    columnHelper.accessor((row) => row.public_comment_count ?? 0, {
      id: 'comments',
      header: ({ column }) => (
        <SortableHeader column={column} label="Comments" className="hidden lg:table-cell" />
      ),
      cell: (info) => {
        const count = info.getValue()
        return count > 0 ? (
          <span className="text-xs font-medium text-civic-navy">{count}</span>
        ) : (
          <span className="text-xs text-slate-300">{'\u2014'}</span>
        )
      },
      meta: { className: 'hidden lg:table-cell' },
      sortingFn: 'basic',
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
  const visibleRows = showAll ? allRows : allRows.slice(0, 10)

  return (
    <div>
      {/* Filters + Sort — single row */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
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
          Hide{' '}
          <CivicTerm
            term="Consent Calendar"
            definition="Routine items grouped for a single vote without discussion. Usually pass unanimously."
          >
            consent calendar
          </CivicTerm>
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
        {filtered.length !== grouped.length && (
          <span className="text-xs text-slate-400 self-center">
            {filtered.length} of {grouped.length} items
          </span>
        )}
        <select
          value={`${sorting[0]?.id ?? 'meeting_date'}-${sorting[0]?.desc !== false ? 'desc' : 'asc'}`}
          onChange={(e) => {
            const [id, dir] = e.target.value.split('-')
            setSorting([{ id, desc: dir === 'desc' }])
          }}
          className="text-sm border border-slate-200 rounded px-2 py-1 text-slate-700 ml-auto"
        >
          <option value="comments-desc">Most discussed first</option>
          <option value="meeting_date-desc">Most recent first</option>
          <option value="meeting_date-asc">Oldest first</option>
          <option value="vote_choice-asc">By vote</option>
          <option value="motion_result-asc">By result</option>
        </select>
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
                    <td key={cell.id} className={`py-2 pr-3 align-top ${meta?.className ?? ''}`}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!showAll && filtered.length > 10 && (
        <button
          onClick={() => setShowAll(true)}
          className="mt-2 text-sm text-civic-navy-light hover:text-civic-navy"
        >
          Show all {filtered.length} items
        </button>
      )}
    </div>
  )
}
