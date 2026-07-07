'use client'

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
import EntityLink from '@/components/EntityLink'
import type { PACContributionRow } from '@/lib/types'

interface DonorAggregate {
  donor_name: string
  donor_employer: string | null
  total_amount: number
  contribution_count: number
  latest_date: string
}

function fmt(n: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(n)
}

interface DonorAggregateInternal extends DonorAggregate {
  earliest_date: string
}

function aggregate(rows: PACContributionRow[]): DonorAggregateInternal[] {
  const map = new Map<string, DonorAggregateInternal>()
  for (const r of rows) {
    const existing = map.get(r.donor_name)
    if (existing) {
      existing.total_amount += r.amount
      existing.contribution_count += 1
      if (r.contribution_date > existing.latest_date) existing.latest_date = r.contribution_date
      if (r.contribution_date < existing.earliest_date) existing.earliest_date = r.contribution_date
    } else {
      map.set(r.donor_name, {
        donor_name: r.donor_name,
        donor_employer: r.donor_employer,
        total_amount: r.amount,
        contribution_count: 1,
        latest_date: r.contribution_date,
        earliest_date: r.contribution_date,
      })
    }
  }
  return Array.from(map.values()).sort((a, b) => b.total_amount - a.total_amount)
}

function fmtDateRange(earliest: string, latest: string): string {
  if (earliest === latest) {
    return new Date(earliest + 'T00:00:00').toLocaleDateString('en-US', {
      month: 'short',
      year: 'numeric',
    })
  }
  const e = new Date(earliest + 'T00:00:00')
  const l = new Date(latest + 'T00:00:00')
  const sameYear = e.getFullYear() === l.getFullYear()
  const eFmt = sameYear
    ? e.toLocaleDateString('en-US', { month: 'short' })
    : e.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
  const lFmt = l.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
  return `${eFmt} – ${lFmt}`
}

const columnHelper = createColumnHelper<DonorAggregateInternal>()

function makeColumns(pacUrlMap: Map<string, string> | null) { return [
  columnHelper.accessor('donor_name', {
    header: ({ column }) => <SortableHeader column={column} label="Donor" />,
    cell: (info) => <EntityLink name={info.getValue()} urlMap={pacUrlMap} className="text-slate-900" />,
  }),
  columnHelper.accessor('donor_employer', {
    header: 'Employer',
    cell: (info) => info.getValue() ?? '·',
    enableSorting: false,
    meta: { className: 'hidden sm:table-cell text-slate-500' },
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
    header: ({ column }) => <SortableHeader column={column} label="When" className="text-right" />,
    cell: (info) => {
      const row = info.row.original
      return (
        <span className="text-slate-500 tabular-nums whitespace-nowrap">
          {fmtDateRange(row.earliest_date, row.latest_date)}
        </span>
      )
    },
    meta: { className: 'text-right hidden md:table-cell' },
  }),
]; }

export default function PACDonorTable({ contributions, pacUrlMap }: { contributions: PACContributionRow[]; pacUrlMap: Map<string, string> | null }) {
  const [search, setSearch] = useState('')
  const [showAll, setShowAll] = useState(false)
  const [sorting, setSorting] = useState<SortingState>([{ id: 'total_amount', desc: true }])

  const aggregated = useMemo(() => aggregate(contributions), [contributions])
  const columns = useMemo(() => makeColumns(pacUrlMap), [pacUrlMap])

  const filtered = useMemo(() => {
    if (!search.trim()) return aggregated
    const q = search.toLowerCase()
    return aggregated.filter(
      (d) => d.donor_name.toLowerCase().includes(q) || (d.donor_employer ?? '').toLowerCase().includes(q),
    )
  }, [aggregated, search])

  const table = useReactTable({
    data: filtered,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  if (aggregated.length === 0) {
    return <p className="text-sm text-slate-500 italic">No contribution data available.</p>
  }

  const allRows = table.getRowModel().rows
  const visibleRows = showAll ? allRows : allRows.slice(0, 25)

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <input
          type="text"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setShowAll(false)
          }}
          placeholder="Search donors or employers…"
          className="w-full sm:w-72 px-3 py-1.5 text-sm border border-slate-200 rounded-md focus:outline-none focus:ring-1 focus:ring-civic-navy/30 focus:border-civic-navy/40"
        />
      </div>

      <div className="flex items-baseline gap-3 mb-3">
        <span className="text-lg font-semibold text-civic-navy tabular-nums">
          {fmt(aggregated.reduce((s, d) => s + d.total_amount, 0))}
        </span>
        <span className="text-sm text-slate-500">
          from {aggregated.length} donor{aggregated.length !== 1 ? 's' : ''}
        </span>
      </div>

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
            {visibleRows.length === 0 ? (
              <tr>
                <td colSpan={4} className="py-6 text-center text-sm text-slate-400 italic">
                  No donors match this search.
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

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
        {!showAll && allRows.length > 25 && (
          <button
            onClick={() => setShowAll(true)}
            className="text-sm text-civic-navy-light hover:text-civic-navy"
          >
            Show all {allRows.length} donors
          </button>
        )}
        {search && (
          <span className="text-xs text-slate-400">
            {filtered.length} of {aggregated.length} donors match
          </span>
        )}
      </div>
    </div>
  )
}
