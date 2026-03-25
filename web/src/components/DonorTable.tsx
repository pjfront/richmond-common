'use client'

import { useState, useMemo } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from '@tanstack/react-table'
import SortableHeader from './SortableHeader'
import type { DonorAggregate, DonorContribution } from '@/lib/types'

type TimePeriod = 'all' | 'before-election' | 'since-election'

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount)
}

function formatShortDate(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
}

/** Aggregate individual contributions into per-donor summaries */
function aggregateContributions(contributions: DonorContribution[]): DonorAggregate[] {
  const donorMap = new Map<string, DonorAggregate>()
  for (const c of contributions) {
    const existing = donorMap.get(c.donor_name)
    if (existing) {
      existing.total_amount += c.amount
      existing.contribution_count += 1
    } else {
      donorMap.set(c.donor_name, {
        donor_name: c.donor_name,
        donor_employer: c.donor_employer,
        total_amount: c.amount,
        contribution_count: 1,
        source: c.source,
        donor_pattern: c.donor_pattern,
      })
    }
  }
  return Array.from(donorMap.values()).sort((a, b) => b.total_amount - a.total_amount)
}

/** Pattern badge styling: informational, not judgmental */
const PATTERN_CONFIG: Record<string, { label: string; className: string; description: string }> = {
  pac: {
    label: 'PAC',
    className: 'bg-purple-100 text-purple-700',
    description: 'Political Action Committee — an organization that pools contributions to support candidates',
  },
  mega: {
    label: 'Major',
    className: 'bg-blue-100 text-blue-700',
    description: 'Top 1% of donors by total amount contributed across all Richmond campaigns',
  },
  grassroots: {
    label: 'Grassroots',
    className: 'bg-green-100 text-green-700',
    description: 'Many small donations (under $250 average) spread across multiple candidates',
  },
  targeted: {
    label: 'Targeted',
    className: 'bg-amber-100 text-amber-700',
    description: 'Larger donations concentrated on one or two specific candidates',
  },
}

function DonorPatternBadge({ pattern }: { pattern: string | null }) {
  if (!pattern || pattern === 'regular') return null
  const config = PATTERN_CONFIG[pattern]
  if (!config) return null
  return (
    <span
      title={config.description}
      className={`inline-block text-xs px-1.5 py-0.5 rounded font-medium ml-1.5 ${config.className}`}
    >
      {config.label}
    </span>
  )
}

const columnHelper = createColumnHelper<DonorAggregate>()

const columns = [
  columnHelper.accessor('donor_name', {
    header: ({ column }) => <SortableHeader column={column} label="Donor" />,
    cell: (info) => (
      <span className="text-slate-900">
        {info.getValue()}
        <DonorPatternBadge pattern={info.row.original.donor_pattern} />
      </span>
    ),
  }),
  columnHelper.accessor('donor_employer', {
    header: 'Employer',
    cell: (info) => info.getValue() ?? '\u2014',
    enableSorting: false,
    meta: { className: 'hidden sm:table-cell' },
  }),
  columnHelper.accessor('total_amount', {
    header: ({ column }) => <SortableHeader column={column} label="Total" className="text-right" />,
    cell: (info) => (
      <span className="font-medium text-slate-900">{formatCurrency(info.getValue())}</span>
    ),
    meta: { className: 'text-right' },
  }),
  columnHelper.accessor('contribution_count', {
    header: ({ column }) => <SortableHeader column={column} label="#" className="text-right" />,
    cell: (info) => <span className="text-slate-500">{info.getValue()}</span>,
    meta: { className: 'text-right' },
  }),
]

/** NetFile public portal for Richmond campaign finance filings */
const NETFILE_PUBLIC_URL = 'https://public.netfile.com/pub2/?AID=RICH'

interface DonorTableProps {
  contributions: DonorContribution[]
  lastElectionDate: string | null
}

export default function DonorTable({ contributions, lastElectionDate }: DonorTableProps) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'total_amount', desc: true },
  ])
  const [showAll, setShowAll] = useState(false)
  const [search, setSearch] = useState('')
  const [showLegend, setShowLegend] = useState(false)
  const [period, setPeriod] = useState<TimePeriod>('all')

  // Filter contributions by time period, then aggregate
  const donors = useMemo(() => {
    let filtered = contributions
    if (lastElectionDate && period !== 'all') {
      if (period === 'before-election') {
        filtered = contributions.filter(c => c.contribution_date <= lastElectionDate)
      } else {
        filtered = contributions.filter(c => c.contribution_date > lastElectionDate)
      }
    }
    return aggregateContributions(filtered)
  }, [contributions, period, lastElectionDate])

  // Compute date range for display
  const dateRange = useMemo(() => {
    if (contributions.length === 0) return null
    const dates = contributions.map(c => c.contribution_date).sort()
    return { earliest: dates[0], latest: dates[dates.length - 1] }
  }, [contributions])

  // Filter donors by search term (name + employer)
  const filtered = useMemo(() => {
    if (!search.trim()) return donors
    const q = search.toLowerCase()
    return donors.filter(
      d =>
        d.donor_name.toLowerCase().includes(q) ||
        (d.donor_employer ?? '').toLowerCase().includes(q)
    )
  }, [donors, search])

  const table = useReactTable({
    data: filtered,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  if (contributions.length === 0) {
    return <p className="text-sm text-slate-500 italic">No contribution data available.</p>
  }

  const allRows = table.getRowModel().rows
  const visibleRows = showAll ? allRows : allRows.slice(0, 10)
  const hasPatterns = donors.some(d => d.donor_pattern && d.donor_pattern !== 'regular')

  // Period label for the description line
  const periodLabel = period === 'all' && dateRange
    ? `${formatShortDate(dateRange.earliest)}\u2013${formatShortDate(dateRange.latest)}`
    : period === 'before-election' && lastElectionDate
      ? `through ${formatShortDate(lastElectionDate)}`
      : period === 'since-election' && lastElectionDate
        ? `since ${formatShortDate(lastElectionDate)}`
        : null

  return (
    <div>
      {/* Time period toggle + search */}
      <div className="mb-3 flex flex-wrap items-center gap-3">
        {lastElectionDate && (
          <div className="flex rounded-md border border-slate-200 text-sm" role="group" aria-label="Contribution time period">
            <button
              onClick={() => { setPeriod('all'); setShowAll(false) }}
              className={`px-3 py-1.5 rounded-l-md transition-colors ${
                period === 'all'
                  ? 'bg-civic-navy text-white'
                  : 'bg-white text-slate-600 hover:bg-slate-50'
              }`}
            >
              All time
            </button>
            <button
              onClick={() => { setPeriod('before-election'); setShowAll(false) }}
              className={`px-3 py-1.5 border-x border-slate-200 transition-colors ${
                period === 'before-election'
                  ? 'bg-civic-navy text-white'
                  : 'bg-white text-slate-600 hover:bg-slate-50'
              }`}
            >
              Before last election
            </button>
            <button
              onClick={() => { setPeriod('since-election'); setShowAll(false) }}
              className={`px-3 py-1.5 rounded-r-md transition-colors ${
                period === 'since-election'
                  ? 'bg-civic-navy text-white'
                  : 'bg-white text-slate-600 hover:bg-slate-50'
              }`}
            >
              Since last election
            </button>
          </div>
        )}
        <input
          type="text"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setShowAll(false) }}
          placeholder="Search donors or employers\u2026"
          className="w-full sm:w-72 px-3 py-1.5 text-sm border border-slate-200 rounded-md focus:outline-none focus:ring-1 focus:ring-civic-navy/30 focus:border-civic-navy/40"
        />
      </div>

      {/* Period context line */}
      {periodLabel && (
        <p className="text-xs text-slate-400 mb-2">
          Showing {donors.length} donors, {periodLabel}
        </p>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="border-b border-slate-200 text-left">
                {headerGroup.headers.map((header) => {
                  const meta = header.column.columnDef.meta as { className?: string } | undefined
                  return (
                    <th key={header.id} className={`py-2 pr-4 font-medium text-slate-600 ${meta?.className ?? ''}`}>
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
            {visibleRows.length === 0 ? (
              <tr>
                <td colSpan={4} className="py-6 text-center text-sm text-slate-400 italic">
                  No contributions in this period.
                </td>
              </tr>
            ) : (
              visibleRows.map((row) => (
                <tr key={row.id} className="border-b border-slate-100">
                  {row.getVisibleCells().map((cell) => {
                    const meta = cell.column.columnDef.meta as { className?: string } | undefined
                    return (
                      <td key={cell.id} className={`py-2 pr-4 ${meta?.className ?? ''}`}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    )
                  })}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Show all / search result count */}
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
        {!showAll && allRows.length > 10 && (
          <button
            onClick={() => setShowAll(true)}
            className="text-sm text-civic-navy-light hover:text-civic-navy"
          >
            Show all {allRows.length} donors
          </button>
        )}
        {search && (
          <span className="text-xs text-slate-400">
            {filtered.length} of {donors.length} donors match
          </span>
        )}
      </div>

      {/* Tag legend + source link */}
      <div className="mt-4 pt-3 border-t border-slate-100 flex flex-wrap items-start justify-between gap-4">
        <div className="text-xs text-slate-400">
          {hasPatterns && (
            <button
              onClick={() => setShowLegend(!showLegend)}
              className="text-slate-500 hover:text-slate-700"
            >
              {showLegend ? 'Hide' : 'What do the tags mean?'}
            </button>
          )}
          {showLegend && (
            <dl className="mt-2 space-y-1.5 text-xs">
              {Object.entries(PATTERN_CONFIG).map(([key, config]) => (
                <div key={key} className="flex items-start gap-2">
                  <dt>
                    <span className={`inline-block px-1.5 py-0.5 rounded font-medium ${config.className}`}>
                      {config.label}
                    </span>
                  </dt>
                  <dd className="text-slate-500">{config.description}</dd>
                </div>
              ))}
              <div className="flex items-start gap-2">
                <dt className="text-slate-400 font-medium min-w-[3rem]">No tag</dt>
                <dd className="text-slate-500">Regular donor — no distinctive giving pattern detected</dd>
              </div>
            </dl>
          )}
        </div>
        <a
          href={NETFILE_PUBLIC_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-slate-400 hover:text-civic-navy-light shrink-0"
        >
          View all filings on NetFile &rarr;
        </a>
      </div>
    </div>
  )
}
