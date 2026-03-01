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
import { useOperatorMode } from './OperatorModeProvider'
import type { DonorAggregate } from '@/lib/types'

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount)
}

/** Format snake_case source identifiers for display */
function formatSource(source: string): string {
  return source
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

/** Pattern badge styling: informational, not judgmental */
const PATTERN_CONFIG: Record<string, { label: string; className: string; operatorOnly?: boolean }> = {
  pac: { label: 'PAC', className: 'bg-purple-100 text-purple-700' },
  mega: { label: 'Major', className: 'bg-blue-100 text-blue-700', operatorOnly: true },
  grassroots: { label: 'Grassroots', className: 'bg-green-100 text-green-700', operatorOnly: true },
  targeted: { label: 'Targeted', className: 'bg-amber-100 text-amber-700', operatorOnly: true },
}

function DonorPatternBadge({ pattern }: { pattern: string | null }) {
  const { isOperator } = useOperatorMode()
  if (!pattern || pattern === 'regular') return null
  const config = PATTERN_CONFIG[pattern]
  if (!config) return null
  if (config.operatorOnly && !isOperator) return null
  return (
    <span className={`inline-block text-xs px-1.5 py-0.5 rounded font-medium ml-1.5 ${config.className}`}>
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
  columnHelper.accessor('source', {
    header: 'Source',
    enableSorting: false,
    cell: (info) => <span className="text-xs text-slate-400">{formatSource(info.getValue())}</span>,
    meta: { className: 'hidden md:table-cell' },
  }),
]

export default function DonorTable({ donors }: { donors: DonorAggregate[] }) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'total_amount', desc: true },
  ])
  const [showAll, setShowAll] = useState(false)

  const data = useMemo(() => donors, [donors])

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  if (donors.length === 0) {
    return <p className="text-sm text-slate-500 italic">No contribution data available.</p>
  }

  const allRows = table.getRowModel().rows
  const visibleRows = showAll ? allRows : allRows.slice(0, 10)

  return (
    <div>
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
            {visibleRows.map((row) => (
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
      {!showAll && allRows.length > 10 && (
        <button
          onClick={() => setShowAll(true)}
          className="mt-2 text-sm text-civic-navy-light hover:text-civic-navy"
        >
          Show all {allRows.length} donors
        </button>
      )}
    </div>
  )
}
