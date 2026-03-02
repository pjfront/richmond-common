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
import Link from 'next/link'
import type { ControversyItem } from '@/lib/types'
import CategoryBadge from './CategoryBadge'
import SortableHeader from './SortableHeader'

interface ControversyLeaderboardProps {
  items: ControversyItem[]
}

export default function ControversyLeaderboard({ items }: ControversyLeaderboardProps) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'controversy_score', desc: true },
  ])

  const columns = useMemo<ColumnDef<ControversyItem>[]>(() => [
    {
      accessorKey: 'controversy_score',
      header: ({ column }) => <SortableHeader column={column} label="Score" />,
      cell: ({ getValue }) => {
        const score = getValue() as number
        return <ControversyScore score={score} />
      },
    },
    {
      accessorKey: 'title',
      header: ({ column }) => <SortableHeader column={column} label="Item" />,
      cell: ({ getValue, row }) => (
        <div className="max-w-md">
          <Link
            href={`/meetings/${row.original.meeting_id}`}
            className="text-civic-navy hover:underline font-medium line-clamp-2"
          >
            {getValue() as string}
          </Link>
          <div className="flex items-center gap-2 mt-1 text-xs text-slate-500">
            <span>{row.original.item_number}</span>
            <span>&middot;</span>
            <span>{formatDate(row.original.meeting_date)}</span>
          </div>
        </div>
      ),
    },
    {
      accessorKey: 'category',
      header: ({ column }) => <SortableHeader column={column} label="Topic" />,
      cell: ({ getValue }) => <CategoryBadge category={getValue() as string | null} />,
    },
    {
      accessorKey: 'vote_tally',
      header: ({ column }) => <SortableHeader column={column} label="Vote" />,
      cell: ({ getValue, row }) => {
        const tally = getValue() as string | null
        const passed = row.original.result === 'passed'
        return (
          <div className="flex items-center gap-1.5">
            <span className="tabular-nums font-medium">{tally ?? '—'}</span>
            {tally && (
              <span className={`text-xs ${passed ? 'text-emerald-600' : 'text-red-600'}`}>
                {passed ? 'passed' : 'failed'}
              </span>
            )}
          </div>
        )
      },
    },
    {
      accessorKey: 'public_comment_count',
      header: ({ column }) => <SortableHeader column={column} label="Comments" />,
      cell: ({ getValue }) => (
        <span className="tabular-nums">{getValue() as number}</span>
      ),
    },
    {
      accessorKey: 'motion_count',
      header: ({ column }) => <SortableHeader column={column} label="Motions" />,
      cell: ({ getValue }) => (
        <span className="tabular-nums">{getValue() as number}</span>
      ),
    },
  ], [])

  const table = useReactTable({
    data: items,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  if (items.length === 0) {
    return <p className="text-slate-500 italic">No controversial items found.</p>
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

function ControversyScore({ score }: { score: number }) {
  const color = score >= 7 ? 'text-red-600 bg-red-50 border-red-200'
    : score >= 4 ? 'text-amber-700 bg-amber-50 border-amber-200'
    : 'text-emerald-700 bg-emerald-50 border-emerald-200'

  return (
    <span className={`inline-block px-2 py-0.5 rounded border text-xs font-bold tabular-nums ${color}`}>
      {score.toFixed(1)}
    </span>
  )
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}
