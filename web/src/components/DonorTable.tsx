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

// ── Helpers ──────────────────────────────────────────────────

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount)
}

function electionYear(dateStr: string): string {
  return new Date(dateStr + 'T00:00:00').getFullYear().toString()
}

// ── Election Cycles ──────────────────────────────────────────

interface ElectionCycle {
  id: string          // 'all' | '2022' | '2024' | 'current'
  label: string       // 'All time' | '2022 Election' | 'Current'
  startAfter: string | null   // contributions > this date (null = from beginning)
  endBy: string | null        // contributions <= this date (null = through today)
}

function buildCycles(electionDates: string[]): ElectionCycle[] {
  if (electionDates.length === 0) return []

  const cycles: ElectionCycle[] = [
    { id: 'all', label: 'All time', startAfter: null, endBy: null },
  ]

  for (let i = 0; i < electionDates.length; i++) {
    const prevDate = i > 0 ? electionDates[i - 1] : null
    cycles.push({
      id: electionYear(electionDates[i]),
      label: `${electionYear(electionDates[i])} Election`,
      startAfter: prevDate,
      endBy: electionDates[i],
    })
  }

  // Current cycle: after the last election through today
  cycles.push({
    id: 'current',
    label: 'Current',
    startAfter: electionDates[electionDates.length - 1],
    endBy: null,
  })

  return cycles
}

function filterByCycle(contributions: DonorContribution[], cycle: ElectionCycle): DonorContribution[] {
  return contributions.filter((c) => {
    if (cycle.startAfter && c.contribution_date <= cycle.startAfter) return false
    if (cycle.endBy && c.contribution_date > cycle.endBy) return false
    return true
  })
}

// ── Sparkline ────────────────────────────────────────────────

/** Aggregate contributions into monthly buckets for the sparkline */
function monthlyBuckets(contributions: DonorContribution[]): { month: string; total: number }[] {
  if (contributions.length === 0) return []
  const map = new Map<string, number>()
  for (const c of contributions) {
    const month = c.contribution_date.slice(0, 7) // YYYY-MM
    map.set(month, (map.get(month) ?? 0) + c.amount)
  }

  // Fill gaps so the sparkline is continuous
  const sorted = Array.from(map.keys()).sort()
  const first = sorted[0]
  const last = sorted[sorted.length - 1]
  const result: { month: string; total: number }[] = []

  let cursor = first
  while (cursor <= last) {
    result.push({ month: cursor, total: map.get(cursor) ?? 0 })
    // Advance one month
    const [y, m] = cursor.split('-').map(Number)
    const next = m === 12 ? `${y + 1}-01` : `${y}-${String(m + 1).padStart(2, '0')}`
    cursor = next
  }

  return result
}

interface SparklineProps {
  contributions: DonorContribution[]
  electionDates: string[]
  activeCycle: ElectionCycle
}

function ContributionSparkline({ contributions, electionDates, activeCycle }: SparklineProps) {
  const buckets = useMemo(() => monthlyBuckets(contributions), [contributions])
  if (buckets.length < 2) return null

  const width = 600
  const height = 60
  const maxVal = Math.max(...buckets.map((b) => b.total))
  if (maxVal === 0) return null

  const xStep = width / (buckets.length - 1)

  // Build area path
  const points = buckets.map((b, i) => ({
    x: i * xStep,
    y: height - (b.total / maxVal) * (height - 4),
  }))
  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ')
  const areaPath = `${linePath} L${width},${height} L0,${height} Z`

  // Compute active cycle highlight region
  let highlightX0 = 0
  let highlightX1 = width
  if (activeCycle.id !== 'all') {
    for (let i = 0; i < buckets.length; i++) {
      if (activeCycle.startAfter && buckets[i].month <= activeCycle.startAfter.slice(0, 7)) {
        highlightX0 = (i + 1) * xStep
      }
      if (activeCycle.endBy && buckets[i].month <= activeCycle.endBy.slice(0, 7)) {
        highlightX1 = i * xStep
      }
    }
    // Clamp
    highlightX0 = Math.max(0, Math.min(highlightX0, width))
    highlightX1 = Math.max(highlightX0, Math.min(highlightX1, width))
  }

  // Election date markers (vertical lines)
  const electionMarkers = electionDates.map((d) => {
    const month = d.slice(0, 7)
    const idx = buckets.findIndex((b) => b.month >= month)
    if (idx < 0) return null
    return { x: idx * xStep, year: electionYear(d) }
  }).filter(Boolean) as { x: number; year: string }[]

  return (
    <div className="mb-4">
      <svg
        viewBox={`0 0 ${width} ${height + 12}`}
        className="w-full h-[72px]"
        preserveAspectRatio="none"
        aria-label="Contribution activity over time"
        role="img"
      >
        {/* Dimmed area for full timeline */}
        <path d={areaPath} fill="#e2e8f0" opacity={activeCycle.id === 'all' ? 0 : 0.4} />

        {/* Active cycle highlight */}
        {activeCycle.id !== 'all' && (
          <clipPath id="cycle-clip">
            <rect x={highlightX0} y={0} width={highlightX1 - highlightX0} height={height} />
          </clipPath>
        )}
        <path
          d={areaPath}
          fill={activeCycle.id === 'all' ? '#cbd5e1' : '#1e3a5f'}
          opacity={activeCycle.id === 'all' ? 0.5 : 0.3}
          clipPath={activeCycle.id !== 'all' ? 'url(#cycle-clip)' : undefined}
        />
        <path
          d={linePath}
          fill="none"
          stroke="#1e3a5f"
          strokeWidth={1.5}
          opacity={0.6}
        />

        {/* Election date markers */}
        {electionMarkers.map((m) => (
          <g key={m.year}>
            <line
              x1={m.x} y1={0} x2={m.x} y2={height}
              stroke="#94a3b8" strokeWidth={1} strokeDasharray="3,3"
            />
            <text
              x={m.x} y={height + 10}
              textAnchor="middle"
              className="fill-slate-400"
              fontSize={9}
            >
              {m.year}
            </text>
          </g>
        ))}
      </svg>
    </div>
  )
}

// ── Donor Pattern Badges ─────────────────────────────────────

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

// ── Aggregation ──────────────────────────────────────────────

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

// ── Table Columns ────────────────────────────────────────────

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

// ── Main Component ───────────────────────────────────────────

const NETFILE_PUBLIC_URL = 'https://public.netfile.com/pub2/?AID=RICH'

interface DonorTableProps {
  contributions: DonorContribution[]
  electionDates: string[]
}

export default function DonorTable({ contributions, electionDates }: DonorTableProps) {
  const cycles = useMemo(() => buildCycles(electionDates), [electionDates])
  const [activeCycleId, setActiveCycleId] = useState('all')
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'total_amount', desc: true },
  ])
  const [showAll, setShowAll] = useState(false)
  const [search, setSearch] = useState('')
  const [showLegend, setShowLegend] = useState(false)

  const activeCycle = cycles.find((c) => c.id === activeCycleId) ?? cycles[0]

  // Filter contributions by active cycle, then aggregate
  const donors = useMemo(() => {
    if (!activeCycle || activeCycle.id === 'all') return aggregateContributions(contributions)
    return aggregateContributions(filterByCycle(contributions, activeCycle))
  }, [contributions, activeCycle])

  // Filter donors by search term
  const filtered = useMemo(() => {
    if (!search.trim()) return donors
    const q = search.toLowerCase()
    return donors.filter(
      (d) =>
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
  const hasPatterns = donors.some((d) => d.donor_pattern && d.donor_pattern !== 'regular')

  return (
    <div>
      {/* Sparkline */}
      {activeCycle && (
        <ContributionSparkline
          contributions={contributions}
          electionDates={electionDates}
          activeCycle={activeCycle}
        />
      )}

      {/* Cycle toggle + search */}
      <div className="mb-3 flex flex-wrap items-center gap-3">
        {cycles.length > 1 && (
          <div className="flex flex-wrap rounded-md border border-slate-200 text-sm" role="group" aria-label="Election cycle">
            {cycles.map((cycle, i) => (
              <button
                key={cycle.id}
                onClick={() => { setActiveCycleId(cycle.id); setShowAll(false) }}
                className={`px-3 py-1.5 transition-colors ${
                  activeCycleId === cycle.id
                    ? 'bg-civic-navy text-white'
                    : 'bg-white text-slate-600 hover:bg-slate-50'
                } ${i === 0 ? 'rounded-l-md' : ''} ${i === cycles.length - 1 ? 'rounded-r-md' : ''} ${i > 0 ? 'border-l border-slate-200' : ''}`}
              >
                {cycle.label}
              </button>
            ))}
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

      {/* Context line */}
      <p className="text-xs text-slate-400 mb-2">
        {donors.length} donor{donors.length !== 1 ? 's' : ''}{activeCycle.id !== 'all' ? `, ${activeCycle.label.toLowerCase()}` : ''}
      </p>

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
