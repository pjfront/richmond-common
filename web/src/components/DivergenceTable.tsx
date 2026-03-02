'use client'

import { useMemo, useState } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  type SortingState,
  type ColumnDef,
  flexRender,
} from '@tanstack/react-table'
import type { CategoryDivergence } from '@/lib/types'
import CategoryBadge from './CategoryBadge'
import SortableHeader from './SortableHeader'

interface DivergenceTableProps {
  divergences: CategoryDivergence[]
}

export default function DivergenceTable({ divergences }: DivergenceTableProps) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'divergence_gap', desc: true },
  ])

  const columns = useMemo<ColumnDef<CategoryDivergence>[]>(() => [
    {
      id: 'pair',
      accessorFn: (row) => `${row.official_a_name} & ${row.official_b_name}`,
      header: ({ column }) => <SortableHeader column={column} label="Pair" />,
      cell: ({ row }) => (
        <span className="font-medium text-slate-700">
          {row.original.official_a_name.split(' ').pop()} &amp;{' '}
          {row.original.official_b_name.split(' ').pop()}
        </span>
      ),
    },
    {
      accessorKey: 'category',
      header: ({ column }) => <SortableHeader column={column} label="Topic" />,
      cell: ({ getValue }) => <CategoryBadge category={getValue() as string} />,
    },
    {
      accessorKey: 'overall_agreement_rate',
      header: ({ column }) => <SortableHeader column={column} label="Overall" />,
      cell: ({ getValue }) => (
        <span className="tabular-nums text-sm">
          {Math.round((getValue() as number) * 100)}%
        </span>
      ),
    },
    {
      accessorKey: 'category_agreement_rate',
      header: ({ column }) => <SortableHeader column={column} label="On Topic" />,
      cell: ({ getValue }) => (
        <span className="tabular-nums text-sm">
          {Math.round((getValue() as number) * 100)}%
        </span>
      ),
    },
    {
      accessorKey: 'divergence_gap',
      header: ({ column }) => <SortableHeader column={column} label="Gap" />,
      cell: ({ getValue }) => {
        const gap = getValue() as number
        const pct = Math.round(gap * 100)
        return (
          <span className="tabular-nums text-sm font-semibold text-red-600">
            -{pct}pp
          </span>
        )
      },
    },
    {
      accessorKey: 'shared_category_votes',
      header: ({ column }) => <SortableHeader column={column} label="Votes" />,
      cell: ({ getValue }) => (
        <span className="tabular-nums text-sm text-slate-500">
          {getValue() as number}
        </span>
      ),
    },
  ], [])

  const table = useReactTable({
    data: divergences,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  if (divergences.length === 0) {
    return (
      <p className="text-slate-500 italic text-sm">
        No significant category divergences found (pairs must differ by 15+ percentage points from their overall alignment).
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
