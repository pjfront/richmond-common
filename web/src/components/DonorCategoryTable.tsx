'use client'

import { useState, useMemo } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getExpandedRowModel,
  type SortingState,
  type ColumnDef,
  flexRender,
} from '@tanstack/react-table'
import type { DonorCategoryPattern } from '@/lib/types'
import CategoryBadge from './CategoryBadge'
import SortableHeader from './SortableHeader'

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount)
}

const PATTERN_LABELS: Record<string, { label: string; className: string }> = {
  pac: { label: 'PAC', className: 'bg-purple-100 text-purple-700' },
  mega: { label: 'Major', className: 'bg-blue-100 text-blue-700' },
  grassroots: { label: 'Grassroots', className: 'bg-green-100 text-green-700' },
  targeted: { label: 'Targeted', className: 'bg-amber-100 text-amber-700' },
}

interface DonorCategoryTableProps {
  patterns: DonorCategoryPattern[]
}

export default function DonorCategoryTable({ patterns }: DonorCategoryTableProps) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'category_concentration', desc: true },
  ])
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  const columns = useMemo<ColumnDef<DonorCategoryPattern>[]>(() => [
    {
      accessorKey: 'donor_name',
      header: ({ column }) => <SortableHeader column={column} label="Donor" />,
      cell: ({ row }) => {
        const pattern = row.original.donor_pattern
        const config = pattern && pattern !== 'regular' ? PATTERN_LABELS[pattern] : null
        return (
          <div>
            <button
              onClick={() => setExpanded((prev) => ({
                ...prev,
                [row.original.donor_id]: !prev[row.original.donor_id],
              }))}
              className="text-left font-medium text-slate-700 hover:text-civic-navy transition-colors"
            >
              <span className="mr-1.5 text-xs text-slate-400">
                {expanded[row.original.donor_id] ? '▼' : '▶'}
              </span>
              {row.original.donor_name}
              {config && (
                <span className={`inline-block text-xs px-1.5 py-0.5 rounded font-medium ml-1.5 ${config.className}`}>
                  {config.label}
                </span>
              )}
            </button>
            {row.original.donor_employer && (
              <p className="text-xs text-slate-400 ml-5">{row.original.donor_employer}</p>
            )}
          </div>
        )
      },
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
      accessorKey: 'recipient_count',
      header: ({ column }) => <SortableHeader column={column} label="Recipients" />,
      cell: ({ getValue }) => (
        <span className="tabular-nums text-sm text-slate-600">{getValue() as number}</span>
      ),
    },
    {
      accessorKey: 'top_category',
      header: ({ column }) => <SortableHeader column={column} label="Top Category" />,
      cell: ({ getValue }) => <CategoryBadge category={getValue() as string} />,
    },
    {
      accessorKey: 'category_concentration',
      header: ({ column }) => <SortableHeader column={column} label="Concentration" />,
      cell: ({ getValue }) => {
        const pct = Math.round((getValue() as number) * 100)
        const colorClass = pct >= 60
          ? 'text-red-600 font-semibold'
          : pct >= 40
            ? 'text-amber-600 font-medium'
            : 'text-slate-600'
        return (
          <span className={`tabular-nums text-sm ${colorClass}`}>
            {pct}%
          </span>
        )
      },
    },
  ], [expanded])

  const table = useReactTable({
    data: patterns,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
  })

  if (patterns.length === 0) {
    return (
      <p className="text-slate-500 italic text-sm">
        No significant donor-category concentration patterns found.
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
            <>
              <tr key={row.id} className="hover:bg-slate-50 transition-colors">
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-4 py-3 text-slate-700">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
              {expanded[row.original.donor_id] && (
                <tr key={`${row.id}-detail`}>
                  <td colSpan={columns.length} className="bg-slate-50 px-4 py-3">
                    <div className="ml-5">
                      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                        Category breakdown (by recipients&apos; vote counts)
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {row.original.category_breakdown.map((cb) => (
                          <div key={cb.category} className="flex items-center gap-1.5">
                            <CategoryBadge category={cb.category} />
                            <span className="text-xs text-slate-500 tabular-nums">
                              {cb.vote_count} votes
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </td>
                </tr>
              )}
            </>
          ))}
        </tbody>
      </table>
    </div>
  )
}
