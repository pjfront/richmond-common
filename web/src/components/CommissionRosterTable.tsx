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
import type { CommissionMember } from '@/lib/types'

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '\u2014'
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
}

function formatRole(role: string): string {
  return role
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

const columnHelper = createColumnHelper<CommissionMember>()

const columns = [
  columnHelper.accessor('name', {
    header: ({ column }) => <SortableHeader column={column} label="Name" />,
    cell: (info) => <span className="font-medium text-slate-900">{info.getValue()}</span>,
  }),
  columnHelper.accessor('role', {
    header: ({ column }) => <SortableHeader column={column} label="Role" />,
    cell: (info) => (
      <span className="text-sm text-slate-600">{formatRole(info.getValue())}</span>
    ),
  }),
  columnHelper.accessor('appointed_by', {
    header: ({ column }) => (
      <SortableHeader column={column} label="Appointed By" className="hidden md:table-cell" />
    ),
    cell: (info) => info.getValue() ?? '\u2014',
    meta: { className: 'hidden md:table-cell text-sm text-slate-500' },
  }),
  columnHelper.accessor('term_end', {
    header: ({ column }) => (
      <SortableHeader column={column} label="Term Ends" className="hidden sm:table-cell" />
    ),
    cell: (info) => {
      const value = info.getValue()
      if (!value) return '\u2014'
      const isExpired = new Date(value) < new Date()
      return (
        <span className={isExpired ? 'text-red-600 font-medium' : 'text-slate-500'}>
          {formatDate(value)}
          {isExpired && ' (expired)'}
        </span>
      )
    },
    meta: { className: 'hidden sm:table-cell text-sm' },
  }),
]

export default function CommissionRosterTable({ members }: { members: CommissionMember[] }) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'name', desc: false },
  ])

  const data = useMemo(() => members, [members])

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  if (members.length === 0) {
    return <p className="text-sm text-slate-500 italic">No members listed.</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id} className="border-b border-slate-200 text-left">
              {headerGroup.headers.map((header) => {
                const meta = header.column.columnDef.meta as { className?: string } | undefined
                return (
                  <th key={header.id} className={`py-2 pr-3 font-medium text-slate-600 ${meta?.className ?? ''}`}>
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
                  <td key={cell.id} className={`py-2 pr-3 ${meta?.className ?? ''}`}>
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
