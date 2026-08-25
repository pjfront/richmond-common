'use client'

/**
 * DonorProfileClient — owns cycle-scope state for the donor profile page.
 *
 * Legacy cycle-scoped donor detail retained for individual profiles:
 * cycle-scope chips + cycle bars timeline + giving table.
 * No independent expenditures (individuals don't file IEs).
 */

import { useMemo, useState } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from '@tanstack/react-table'
import SortableHeader from '@/components/SortableHeader'
import type { DonorOutgoingRow } from '@/lib/types'

// ─── Types ──────────────────────────────────────────────────────────────

type CycleScope = 'current' | 'last2' | 'all'

interface CycleBar {
  cycle: number
  total: number
}

interface RecipientAggregate {
  recipient_committee_name: string
  recipient_candidate_name: string | null
  total_amount: number
  contribution_count: number
  latest_date: string
}

interface Props {
  outgoing: DonorOutgoingRow[]
  cycleBars: CycleBar[]
  donorDisplay: string
}

// ─── Helpers ────────────────────────────────────────────────────────────

function fmt(n: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(n)
}

function fmtShort(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`
  if (n >= 10_000) return `$${Math.round(n / 1000)}k`
  if (n >= 1_000) return `$${(n / 1000).toFixed(1)}k`
  if (n > 0) return `$${Math.round(n)}`
  return '–'
}

function cycleOfDate(dateIso: string): number | null {
  const year = parseInt(dateIso.slice(0, 4), 10)
  if (Number.isNaN(year)) return null
  return year % 2 === 0 ? year : year + 1
}

function aggregate(rows: DonorOutgoingRow[]): RecipientAggregate[] {
  const map = new Map<string, RecipientAggregate>()
  for (const r of rows) {
    const key = r.recipient_committee_name
    const existing = map.get(key)
    if (existing) {
      existing.total_amount += r.amount
      existing.contribution_count += 1
      if (r.contribution_date > existing.latest_date) existing.latest_date = r.contribution_date
    } else {
      map.set(key, {
        recipient_committee_name: r.recipient_committee_name,
        recipient_candidate_name: r.recipient_candidate_name,
        total_amount: r.amount,
        contribution_count: 1,
        latest_date: r.contribution_date,
      })
    }
  }
  return Array.from(map.values()).sort((a, b) => b.total_amount - a.total_amount)
}

// ─── Table columns ──────────────────────────────────────────────────────

const columnHelper = createColumnHelper<RecipientAggregate>()

const columns = [
  columnHelper.accessor('recipient_committee_name', {
    header: ({ column }) => <SortableHeader column={column} label="Recipient" />,
    cell: (info) => {
      const candidate = info.row.original.recipient_candidate_name
      return (
        <div>
          <div className="text-slate-900">{info.getValue()}</div>
          {candidate && (
            <div className="text-xs text-slate-500 mt-0.5">Candidate: {candidate}</div>
          )}
        </div>
      )
    },
  }),
  columnHelper.accessor('total_amount', {
    header: ({ column }) => <SortableHeader column={column} label="Total" className="text-right" />,
    cell: (info) => (
      <span className="font-medium text-slate-900 tabular-nums">{fmt(info.getValue())}</span>
    ),
    meta: { className: 'text-right' },
  }),
  columnHelper.accessor('contribution_count', {
    header: ({ column }) => <SortableHeader column={column} label="#" className="text-right" />,
    cell: (info) => <span className="text-slate-500 tabular-nums">{info.getValue()}</span>,
    meta: { className: 'text-right' },
  }),
  columnHelper.accessor('latest_date', {
    header: ({ column }) => <SortableHeader column={column} label="Latest" className="text-right" />,
    cell: (info) => (
      <span className="text-slate-500 tabular-nums">
        {new Date(info.getValue() + 'T00:00:00').toLocaleDateString('en-US', {
          month: 'short',
          year: 'numeric',
        })}
      </span>
    ),
    meta: { className: 'text-right hidden sm:table-cell' },
  }),
]

// ─── Component ──────────────────────────────────────────────────────────

export default function DonorProfileClient({
  outgoing,
  cycleBars,
  donorDisplay,
}: Props) {
  const currentCycle = useMemo(() => {
    const y = new Date().getFullYear()
    return y % 2 === 0 ? y : y + 1
  }, [])

  const [cycleScope, setCycleScope] = useState<CycleScope>('current')
  const [sorting, setSorting] = useState<SortingState>([{ id: 'total_amount', desc: true }])

  // Filter outgoing rows by cycle scope
  const activeCycles = useMemo(() => {
    if (cycleScope === 'all') return null
    if (cycleScope === 'last2') return new Set([currentCycle - 2, currentCycle])
    return new Set([currentCycle])
  }, [cycleScope, currentCycle])

  const filteredOutgoing = useMemo(() => {
    if (!activeCycles) return outgoing
    return outgoing.filter((o) => {
      const cy = cycleOfDate(o.contribution_date)
      return cy !== null && activeCycles.has(cy)
    })
  }, [outgoing, activeCycles])

  // Filter cycle bars by scope for totals
  const filteredBars = useMemo(() => {
    if (!activeCycles) return cycleBars
    return cycleBars.filter((b) => activeCycles.has(b.cycle))
  }, [cycleBars, activeCycles])

  const scopeLabels: Record<CycleScope, string> = {
    current: `${currentCycle} cycle`,
    last2: `${currentCycle - 2}–${currentCycle}`,
    all: 'All time',
  }
  const scopeSubLabels: Record<CycleScope, string> = {
    current: 'This election',
    last2: 'Last two cycles',
    all: 'Lifetime',
  }

  const aggregated = useMemo(() => aggregate(filteredOutgoing), [filteredOutgoing])
  const table = useReactTable({
    data: aggregated,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  return (
    <>
      {/* Scope chips */}
      <div className="mb-5">
        <div className="flex flex-wrap items-stretch gap-2">
          {(['current', 'last2', 'all'] as CycleScope[]).map((s) => {
            const active = cycleScope === s
            return (
              <button
                key={s}
                type="button"
                onClick={() => setCycleScope(s)}
                aria-pressed={active}
                className={`group flex flex-col items-start text-left rounded-lg px-4 py-2.5 border transition-all ${
                  active
                    ? 'bg-civic-amber border-civic-amber text-white shadow-sm'
                    : 'bg-white border-slate-200 text-slate-700 hover:border-civic-amber/60 hover:bg-civic-amber/[0.04]'
                }`}
              >
                <span className="text-sm font-semibold tabular-nums">
                  {scopeLabels[s]}
                </span>
                <span
                  className={`text-[11px] leading-tight mt-0.5 ${
                    active
                      ? 'text-white/85'
                      : 'text-slate-500 group-hover:text-slate-600'
                  }`}
                >
                  {scopeSubLabels[s]}
                </span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Cycle bars timeline */}
      {cycleBars.length > 0 && (
        <CycleBarsInline
          bars={cycleBars}
          activeCycles={activeCycles}
          donorDisplay={donorDisplay}
          filteredTotal={filteredBars.reduce((s, b) => s + b.total, 0)}
        />
      )}

      {/* Giving table */}
      {aggregated.length > 0 ? (
        <section className="mb-6">
          <div className="border-l-4 border-civic-amber/60 bg-civic-amber/[0.03] rounded-r-lg p-5 sm:p-6">
            <h2 className="text-xs font-semibold text-civic-amber uppercase tracking-widest mb-3">
              Where the money went
            </h2>
            <p className="text-[15px] text-slate-700 leading-[1.8] mb-4">
              <strong>{donorDisplay}</strong> appears as a donor on{' '}
              <strong>{aggregated.length.toLocaleString()}</strong> committee
              filing{aggregated.length === 1 ? '' : 's'} in this view, totaling{' '}
              <strong>
                {fmt(aggregated.reduce((s, r) => s + r.total_amount, 0))}
              </strong>
              .
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  {table.getHeaderGroups().map((hg) => (
                    <tr key={hg.id} className="border-b border-slate-200 text-left">
                      {hg.headers.map((header) => {
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
                  {table.getRowModel().rows.map((row) => (
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
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      ) : (
        <section className="mb-6">
          <div className="border border-slate-200 rounded-lg p-5 sm:p-6 text-center">
            <p className="text-sm text-slate-500 italic">
              No contributions match the current cycle selection.
            </p>
          </div>
        </section>
      )}
    </>
  )
}

// ─── Cycle bars inline SVG ──────────────────────────────────────────────

function CycleBarsInline({
  bars,
  activeCycles,
  donorDisplay,
  filteredTotal,
}: {
  bars: CycleBar[]
  activeCycles: Set<number> | null
  donorDisplay: string
  filteredTotal: number
}) {
  const W = 480
  const H = 80
  const PAD_Y = 10
  const GAP = 8
  const barW = (W - GAP * (bars.length - 1)) / bars.length
  const maxVal = Math.max(...bars.map((b) => b.total), 1)

  const topBar = bars.reduce((a, b) => (a.total > b.total ? a : b), bars[0])

  return (
    <section className="mb-6">
      <div className="border border-civic-navy/15 bg-civic-navy/[0.02] rounded-lg p-5 sm:p-6">
        <h2 className="text-xs font-semibold text-civic-navy uppercase tracking-widest mb-2">
          Giving across cycles
        </h2>
        <p className="text-[14px] text-slate-700 leading-snug mb-4">
          Across {bars.length} cycles, <strong>{donorDisplay}</strong>{' '}
          {activeCycles ? (
            <>
              contributed <strong>{fmt(filteredTotal)}</strong> in the
              selected view, peaking in <strong>{topBar.cycle}</strong> (
              <strong>{fmtShort(topBar.total)}</strong>).
            </>
          ) : (
            <>
              contributed <strong>{fmt(filteredTotal)}</strong> across all
              cycles, peaking in <strong>{topBar.cycle}</strong> (
              <strong>{fmtShort(topBar.total)}</strong>).
            </>
          )}
        </p>

        <svg
          viewBox={`0 0 ${W} ${H + 18}`}
          width="100%"
          height="auto"
          role="img"
          aria-label={`Per-cycle giving across ${bars.length} election cycles`}
          className="overflow-visible max-w-[32rem]"
          preserveAspectRatio="xMinYMid meet"
        >
          {bars.map((b, i) => {
            const inScope = !activeCycles || activeCycles.has(b.cycle)
            const ratio = maxVal > 0 ? b.total / maxVal : 0
            const h = b.total === 0 ? 1 : Math.max(2, ratio * (H - PAD_Y))
            const x = i * (barW + GAP)
            const y = H - h

            return (
              <g key={b.cycle}>
                <rect
                  x={x}
                  y={PAD_Y}
                  width={barW}
                  height={H - PAD_Y}
                  fill={inScope ? 'rgba(30, 58, 95, 0.04)' : 'rgba(30, 58, 95, 0.02)'}
                  rx={2}
                  stroke={inScope ? 'rgba(30, 58, 95, 0.22)' : 'rgba(30, 58, 95, 0.08)'}
                  strokeWidth={1}
                />
                <rect
                  x={x}
                  y={y}
                  width={barW}
                  height={h}
                  fill={inScope ? '#d97706' : '#cbd5e1'}
                  rx={2}
                  opacity={inScope ? 1 : 0.35}
                >
                  <title>
                    {b.cycle}: {fmtShort(b.total)}
                    {!inScope ? ' (outside selected scope)' : ''}
                  </title>
                </rect>
                <text
                  x={x + barW / 2}
                  y={H + 12}
                  textAnchor="middle"
                  fontSize={11}
                  fill={inScope ? '#475569' : '#94a3b8'}
                  fontWeight={inScope ? 500 : 400}
                  pointerEvents="none"
                >
                  {b.cycle}
                </text>
                {b.total > 0 && (
                  <text
                    x={x + barW / 2}
                    y={Math.max(8, y - 2)}
                    textAnchor="middle"
                    fontSize={10}
                    fill="#1e3a5f"
                    fontWeight={600}
                    pointerEvents="none"
                  >
                    {fmtShort(b.total)}
                  </text>
                )}
              </g>
            )
          })}
        </svg>
      </div>
    </section>
  )
}
