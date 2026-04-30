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
import type { PACOutgoingRow } from '@/lib/types'

interface RecipientAggregate {
  recipient_committee_name: string
  recipient_candidate_name: string | null
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

function aggregate(rows: PACOutgoingRow[]): RecipientAggregate[] {
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

const columnHelper = createColumnHelper<RecipientAggregate>()

const columns = [
  columnHelper.accessor('recipient_committee_name', {
    header: ({ column }) => <SortableHeader column={column} label="Recipient committee" />,
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

export default function PACOutgoingTable({ outgoing }: { outgoing: PACOutgoingRow[] }) {
  const [sorting, setSorting] = useState<SortingState>([{ id: 'total_amount', desc: true }])

  const aggregated = useMemo(() => aggregate(outgoing), [outgoing])

  const table = useReactTable({
    data: aggregated,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  if (aggregated.length === 0) {
    return <p className="text-sm text-slate-500 italic">No outgoing flows tracked.</p>
  }

  return (
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
  )
}
