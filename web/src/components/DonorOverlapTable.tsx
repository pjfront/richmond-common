'use client'

import { useState, useMemo } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  type SortingState,
  type ColumnDef,
  flexRender,
} from '@tanstack/react-table'
import type { DonorOverlap } from '@/lib/types'
import SortableHeader from './SortableHeader'

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount)
}

interface DonorOverlapTableProps {
  overlaps: DonorOverlap[]
}

export default function DonorOverlapTable({ overlaps }: DonorOverlapTableProps) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'recipients_count', desc: true },
  ])

  const columns = useMemo<ColumnDef<DonorOverlap>[]>(() => [
    {
      accessorKey: 'donor_name',
      header: ({ column }) => <SortableHeader column={column} label="Donor" />,
      cell: ({ row }) => (
        <div>
          <span className="font-medium text-slate-700">{row.original.donor_name}</span>
          {row.original.donor_employer && (
            <p className="text-xs text-slate-400">{row.original.donor_employer}</p>
          )}
        </div>
      ),
    },
    {
      accessorKey: 'total_contributed',
      header: ({ column }) => <SortableHeader column={column} label="Total" />,
      cell: ({ getValue }) => (
        <span className="tabular-nums text-sm font-medium text-slate-700">
          {formatCurrency(getValue() as number)}
        </span>
      ),
    },
    {
      id: 'recipients_count',
      accessorFn: (row) => row.recipients.length,
      header: ({ column }) => <SortableHeader column={column} label="Recipients" />,
      cell: ({ getValue }) => (
        <span className="tabular-nums text-sm font-semibold text-civic-navy">
          {getValue() as number}
        </span>
      ),
    },
    {
      id: 'recipients_detail',
      header: 'Distribution',
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {row.original.recipients.map((r) => (
            <span key={r.official_id} className="text-xs text-slate-600">
              <span className="font-medium">{r.official_name.split(' ').pop()}</span>
              {' '}
              <span className="text-slate-400 tabular-nums">
                {formatCurrency(r.amount)} ({r.contribution_count})
              </span>
            </span>
          ))}
        </div>
      ),
    },
  ], [])

  const table = useReactTable({
    data: overlaps,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  if (overlaps.length === 0) {
    return (
      <p className="text-slate-500 italic text-sm">
        No donors contributing to multiple officials found.
      </p>
    )
  }

  return (
    <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 border-b border-slate-200">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => (
                <th key={h.id} className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                  {flexRender(h.column.columnDef.header, h.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody className="divide-y divide-slate-100">
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id} className="hover:bg-slate-50 transition-colors">
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-4 py-3 text-slate-700">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
