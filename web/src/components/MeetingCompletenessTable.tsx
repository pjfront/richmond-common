'use client'

import { useState } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  createColumnHelper,
  flexRender,
  type SortingState,
} from '@tanstack/react-table'
import SortableHeader from './SortableHeader'
import type { MeetingCompleteness } from '@/lib/types'

const columnHelper = createColumnHelper<MeetingCompleteness>()

function CheckMark({ value }: { value: boolean }) {
  return value ? (
    <span className="text-green-600" title="Available">&#10003;</span>
  ) : (
    <span className="text-slate-300" title="Missing">&#8212;</span>
  )
}

function ScoreBadge({ score }: { score: number }) {
  let color = 'bg-green-100 text-green-800'
  if (score < 50) color = 'bg-red-100 text-red-800'
  else if (score < 80) color = 'bg-amber-100 text-amber-800'

  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${color}`}>
      {score}
    </span>
  )
}

const columns = [
  columnHelper.accessor('meeting_date', {
    header: ({ column }) => <SortableHeader column={column} label="Date" />,
    cell: (info) => (
      <a
        href={`/meetings/${info.row.original.meeting_id}`}
        className="text-civic-navy hover:underline"
      >
        {info.getValue()}
      </a>
    ),
  }),
  columnHelper.accessor('meeting_type', {
    header: ({ column }) => <SortableHeader column={column} label="Type" />,
    cell: (info) => (
      <span className="capitalize text-slate-600">{info.getValue()}</span>
    ),
  }),
  columnHelper.accessor('agenda_item_count', {
    header: ({ column }) => <SortableHeader column={column} label="Items" />,
    cell: (info) => {
      const v = info.getValue()
      return <span className={v === 0 ? 'text-red-600 font-medium' : 'text-slate-900'}>{v}</span>
    },
  }),
  columnHelper.accessor('vote_count', {
    header: ({ column }) => <SortableHeader column={column} label="Votes" />,
    cell: (info) => {
      const v = info.getValue()
      return <span className={v === 0 ? 'text-red-600 font-medium' : 'text-slate-900'}>{v}</span>
    },
  }),
  columnHelper.accessor('attendance_count', {
    header: ({ column }) => <SortableHeader column={column} label="Attend." />,
    cell: (info) => {
      const v = info.getValue()
      return <span className={v === 0 ? 'text-amber-600 font-medium' : 'text-slate-900'}>{v}</span>
    },
  }),
  columnHelper.accessor('has_minutes', {
    header: 'Min.',
    cell: (info) => <CheckMark value={info.getValue()} />,
  }),
  columnHelper.accessor('has_agenda', {
    header: 'Agd.',
    cell: (info) => <CheckMark value={info.getValue()} />,
  }),
  columnHelper.accessor('has_video', {
    header: 'Vid.',
    cell: (info) => <CheckMark value={info.getValue()} />,
  }),
  columnHelper.accessor('completeness_score', {
    header: ({ column }) => <SortableHeader column={column} label="Score" />,
    cell: (info) => <ScoreBadge score={info.getValue()} />,
  }),
]

export default function MeetingCompletenessTable({ data }: { data: MeetingCompleteness[] }) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'meeting_date', desc: true },
  ])

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id} className="border-b border-slate-200">
              {hg.headers.map((header) => (
                <th
                  key={header.id}
                  className="px-3 py-2 text-left text-xs font-medium text-slate-500 uppercase tracking-wider"
                >
                  {header.isPlaceholder
                    ? null
                    : flexRender(header.column.columnDef.header, header.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody className="divide-y divide-slate-100">
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id} className="hover:bg-slate-50">
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-3 py-2 whitespace-nowrap">
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
