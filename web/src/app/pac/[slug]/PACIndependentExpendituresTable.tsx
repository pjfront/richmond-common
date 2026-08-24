'use client'

/**
 * PACIndependentExpendituresTable. Aggregates a PAC's IE rows by
 * (candidate, direction) and presents the ledger of who they spent on
 * and against — the data layer between "PAC contributions to other
 * committees" and the underlying donor flow.
 *
 * IEs differ from contributions: the money does NOT pass through the
 * candidate's committee. The PAC pays a vendor (mailer, ad agency,
 * canvasser) directly, naming the candidate on the FPPC filing. The
 * candidate is the BENEFICIARY of the spend, not the recipient.
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
import EntityLink, { type EntityUrlMap } from '@/components/EntityLink'
import type { PACIndependentExpenditureRow } from '@/lib/types'

interface CandidateAggregate {
  candidate_name: string
  direction: 'S' | 'O' | null
  total_amount: number
  expenditure_count: number
  earliest_date: string
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

function aggregate(
  rows: PACIndependentExpenditureRow[],
): CandidateAggregate[] {
  const map = new Map<string, CandidateAggregate>()
  for (const r of rows) {
    if (!r.candidate_name) continue
    const key = `${r.candidate_name}|${r.support_or_oppose ?? ''}`
    const existing = map.get(key)
    if (existing) {
      existing.total_amount += r.amount
      existing.expenditure_count += 1
      if (r.expenditure_date > existing.latest_date)
        existing.latest_date = r.expenditure_date
      if (r.expenditure_date < existing.earliest_date)
        existing.earliest_date = r.expenditure_date
    } else {
      map.set(key, {
        candidate_name: r.candidate_name,
        direction: r.support_or_oppose,
        total_amount: r.amount,
        expenditure_count: 1,
        earliest_date: r.expenditure_date,
        latest_date: r.expenditure_date,
      })
    }
  }
  return Array.from(map.values()).sort(
    (a, b) => b.total_amount - a.total_amount,
  )
}

const columnHelper = createColumnHelper<CandidateAggregate>()

function makeColumns(pacUrlMap: EntityUrlMap | null) { return [
  columnHelper.accessor('candidate_name', {
    header: ({ column }) => (
      <SortableHeader column={column} label="Candidate or beneficiary" />
    ),
    cell: (info) => {
      const direction = info.row.original.direction
      return (
        <div className="flex items-baseline gap-2">
          <EntityLink name={info.getValue()} urlMap={pacUrlMap} className="text-slate-900" />
          {direction === 'S' && (
            <span className="text-[10px] font-semibold uppercase tracking-wide text-emerald-700 bg-emerald-50 border border-emerald-200 rounded px-1.5 py-0.5">
              Support
            </span>
          )}
          {direction === 'O' && (
            <span className="text-[10px] font-semibold uppercase tracking-wide text-red-700 bg-red-50 border border-red-200 rounded px-1.5 py-0.5">
              Oppose
            </span>
          )}
        </div>
      )
    },
  }),
  columnHelper.accessor('total_amount', {
    header: ({ column }) => (
      <SortableHeader column={column} label="Total" className="text-right" />
    ),
    cell: (info) => (
      <span className="font-medium text-slate-900 tabular-nums">
        {fmt(info.getValue())}
      </span>
    ),
    meta: { className: 'text-right' },
  }),
  columnHelper.accessor('expenditure_count', {
    header: ({ column }) => (
      <SortableHeader column={column} label="#" className="text-right" />
    ),
    cell: (info) => (
      <span className="text-slate-500 tabular-nums">{info.getValue()}</span>
    ),
    meta: { className: 'text-right' },
  }),
  columnHelper.accessor('latest_date', {
    header: ({ column }) => (
      <SortableHeader column={column} label="When" className="text-right" />
    ),
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

export default function PACIndependentExpendituresTable({
  expenditures,
  pacUrlMap,
}: {
  expenditures: PACIndependentExpenditureRow[]
  pacUrlMap: EntityUrlMap | null
}) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'total_amount', desc: true },
  ])

  const aggregated = useMemo(() => aggregate(expenditures), [expenditures])
  const columns = useMemo(() => makeColumns(pacUrlMap), [pacUrlMap])

  const table = useReactTable({
    data: aggregated,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  if (aggregated.length === 0) {
    return (
      <p className="text-sm text-slate-500 italic">
        No independent expenditures tracked.
      </p>
    )
  }

  const totalAmount = aggregated.reduce((s, a) => s + a.total_amount, 0)
  const supportTotal = aggregated
    .filter((a) => a.direction === 'S')
    .reduce((s, a) => s + a.total_amount, 0)
  const opposeTotal = aggregated
    .filter((a) => a.direction === 'O')
    .reduce((s, a) => s + a.total_amount, 0)

  return (
    <div>
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 mb-3">
        <span className="text-lg font-semibold text-civic-navy tabular-nums">
          {fmt(totalAmount)}
        </span>
        <span className="text-sm text-slate-500">
          across {aggregated.length} candidate
          {aggregated.length !== 1 ? 's' : ''}
        </span>
        {supportTotal > 0 && (
          <span className="text-xs text-emerald-700">
            {fmt(supportTotal)} support
          </span>
        )}
        {opposeTotal > 0 && (
          <span className="text-xs text-red-700">
            {fmt(opposeTotal)} oppose
          </span>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b border-slate-200 text-left">
                {hg.headers.map((header) => {
                  const meta = header.column.columnDef.meta as
                    | { className?: string }
                    | undefined
                  return (
                    <th
                      key={header.id}
                      className={`py-2 pr-4 font-medium text-slate-600 ${meta?.className ?? ''}`}
                    >
                      {header.isPlaceholder
                        ? null
                        : flexRender(
                            header.column.columnDef.header,
                            header.getContext(),
                          )}
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
                  const meta = cell.column.columnDef.meta as
                    | { className?: string }
                    | undefined
                  return (
                    <td
                      key={cell.id}
                      className={`py-2 pr-4 ${meta?.className ?? ''}`}
                    >
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext(),
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
