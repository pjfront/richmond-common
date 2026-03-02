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
import type { CategoryStats } from '@/lib/types'
import CategoryBadge from './CategoryBadge'
import SortableHeader from './SortableHeader'

interface CategoryStatsTableProps {
  stats: CategoryStats[]
}

export default function CategoryStatsTable({ stats }: CategoryStatsTableProps) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'item_count', desc: true },
  ])

  const columns = useMemo<ColumnDef<CategoryStats>[]>(() => [
    {
      accessorKey: 'category',
      header: ({ column }) => <SortableHeader column={column} label="Topic" />,
      cell: ({ getValue }) => <CategoryBadge category={getValue() as string} />,
    },
    {
      accessorKey: 'item_count',
      header: ({ column }) => <SortableHeader column={column} label="Items" />,
      cell: ({ getValue, row }) => (
        <span className="tabular-nums">
          {getValue() as number}
          <span className="text-slate-400 text-xs ml-1">
            ({row.original.percentage_of_agenda}%)
          </span>
        </span>
      ),
    },
    {
      accessorKey: 'vote_count',
      header: ({ column }) => <SortableHeader column={column} label="Votes" />,
      cell: ({ getValue }) => (
        <span className="tabular-nums">{getValue() as number}</span>
      ),
    },
    {
      accessorKey: 'split_vote_count',
      header: ({ column }) => <SortableHeader column={column} label="Split Votes" />,
      cell: ({ getValue, row }) => {
        const split = getValue() as number
        const total = row.original.vote_count
        const pct = total > 0 ? Math.round((split / total) * 100) : 0
        return (
          <span className="tabular-nums">
            {split}
            {total > 0 && (
              <span className="text-slate-400 text-xs ml-1">({pct}%)</span>
            )}
          </span>
        )
      },
    },
    {
      accessorKey: 'avg_controversy_score',
      header: ({ column }) => <SortableHeader column={column} label="Avg Controversy" />,
      cell: ({ getValue }) => {
        const score = getValue() as number
        return (
          <span className="tabular-nums">
            <ControversyBar score={score} />
          </span>
        )
      },
    },
    {
      accessorKey: 'total_public_comments',
      header: ({ column }) => <SortableHeader column={column} label="Public Comments" />,
      cell: ({ getValue }) => (
        <span className="tabular-nums">{getValue() as number}</span>
      ),
    },
  ], [])

  const table = useReactTable({
    data: stats,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  if (stats.length === 0) {
    return <p className="text-slate-500 italic">No category data available.</p>
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

function ControversyBar({ score }: { score: number }) {
  const maxScore = 10
  const pct = Math.min((score / maxScore) * 100, 100)
  const color = score >= 5 ? 'bg-red-500' : score >= 3 ? 'bg-amber-500' : 'bg-emerald-500'

  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-2 bg-slate-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-slate-600">{score.toFixed(1)}</span>
    </div>
  )
}
