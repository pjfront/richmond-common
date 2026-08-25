'use client'

import { useId, useMemo, useState } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from '@tanstack/react-table'
import CampaignEntitySortableHeader from '@/components/CampaignEntitySortableHeader'
import CsvDownloadButton from '@/components/CsvDownloadButton'
import EntityLink, { type EntityUrlMap } from '@/components/EntityLink'
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

function makeColumns(pacUrlMap: EntityUrlMap | null) {
  return [
    columnHelper.accessor('recipient_committee_name', {
      header: ({ column }) => (
        <CampaignEntitySortableHeader
          column={column}
          label="Recipient committee"
        />
      ),
      cell: (info) => {
        const candidate = info.row.original.recipient_candidate_name
        return (
          <div>
            <EntityLink
              name={info.getValue()}
              urlMap={pacUrlMap}
              className="inline-flex min-h-11 items-center rounded-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-civic-navy focus:ring-offset-2"
            />
            {candidate && (
              <div className="text-xs text-slate-500 mt-0.5">
                Candidate: {candidate}
              </div>
            )}
          </div>
        )
      },
    }),
    columnHelper.accessor('total_amount', {
      header: ({ column }) => (
        <CampaignEntitySortableHeader
          column={column}
          label="Reported total"
          className="justify-end"
        />
      ),
      cell: (info) => (
        <span className="font-medium text-slate-900 tabular-nums">
          {fmt(info.getValue())}
        </span>
      ),
      meta: { className: 'text-right' },
    }),
    columnHelper.accessor('contribution_count', {
      header: ({ column }) => (
        <CampaignEntitySortableHeader
          column={column}
          label="Records"
          className="justify-end"
        />
      ),
      cell: (info) => (
        <span className="text-slate-500 tabular-nums">{info.getValue()}</span>
      ),
      meta: { className: 'text-right' },
    }),
    columnHelper.accessor('latest_date', {
      header: ({ column }) => (
        <CampaignEntitySortableHeader
          column={column}
          label="Latest filing date"
          className="justify-end"
        />
      ),
      cell: (info) => (
        <span className="text-slate-500 tabular-nums">
          {new Date(info.getValue() + 'T00:00:00').toLocaleDateString(
            'en-US',
            {
              month: 'short',
              year: 'numeric',
            },
          )}
        </span>
      ),
      meta: { className: 'text-right hidden sm:table-cell' },
    }),
  ]
}

export default function PACOutgoingTable({
  outgoing,
  pacUrlMap,
}: {
  outgoing: PACOutgoingRow[]
  pacUrlMap: EntityUrlMap | null
}) {
  const sortId = useId()
  const [sorting, setSorting] = useState<SortingState>([{ id: 'total_amount', desc: true }])

  const aggregated = useMemo(() => aggregate(outgoing), [outgoing])
  const columns = useMemo(() => makeColumns(pacUrlMap), [pacUrlMap])
  const csvRows = useMemo(
    () =>
      outgoing.map((row) => ({
        recipient_committee_name: row.recipient_committee_name,
        recipient_committee_id: row.recipient_committee_id,
        recipient_candidate_name: row.recipient_candidate_name,
        amount: row.amount,
        contribution_date: row.contribution_date,
        contribution_type: row.contribution_type,
        filing_id: row.filing_id,
      })),
    [outgoing],
  )

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

  const rows = table.getRowModel().rows

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-600">
          {aggregated.length.toLocaleString()} recipient committee
          {aggregated.length === 1 ? '' : 's'}
        </p>
        <CsvDownloadButton
          filename="richmond-committee-outgoing-filing-records.csv"
          columns={[
            'recipient_committee_name',
            'recipient_committee_id',
            'recipient_candidate_name',
            'amount',
            'contribution_date',
            'contribution_type',
            'filing_id',
          ]}
          rows={csvRows}
        />
      </div>

      <div className="mb-3 md:hidden">
        <label htmlFor={sortId} className="mb-1 block text-sm font-medium text-slate-700">
          Sort recipient records
        </label>
        <select
          id={sortId}
          value={sorting[0]?.id ?? 'total_amount'}
          onChange={(event) => {
            const id = event.target.value
            setSorting([{ id, desc: id !== 'recipient_committee_name' }])
          }}
          className="min-h-11 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-base focus:border-civic-navy focus:outline-none focus:ring-2 focus:ring-civic-navy/30"
        >
          <option value="total_amount">Reported total</option>
          <option value="recipient_committee_name">Recipient committee</option>
          <option value="contribution_count">Number of records</option>
          <option value="latest_date">Latest filing date</option>
        </select>
      </div>

      <ul className="space-y-3 md:hidden" aria-label="Outgoing committee contribution totals">
        {rows.map((row) => {
          const recipient = row.original
          return (
            <li key={row.id} className="rounded-md border border-slate-200 p-4 text-sm">
              <p className="font-medium text-slate-900">
                <EntityLink
                  name={recipient.recipient_committee_name}
                  urlMap={pacUrlMap}
                  className="inline-flex min-h-11 items-center rounded-sm focus:outline-none focus:ring-2 focus:ring-civic-navy focus:ring-offset-2"
                />
              </p>
              {recipient.recipient_candidate_name ? (
                <p className="mt-1 text-slate-600">
                  Candidate: {recipient.recipient_candidate_name}
                </p>
              ) : null}
              <p className="mt-2 text-slate-700">
                {fmt(recipient.total_amount)} across {recipient.contribution_count}{' '}
                record{recipient.contribution_count === 1 ? '' : 's'} &middot; latest{' '}
                {new Date(`${recipient.latest_date}T00:00:00`).toLocaleDateString('en-US', {
                  month: 'short',
                  year: 'numeric',
                })}
              </p>
            </li>
          )
        })}
      </ul>

      <div className="hidden md:block">
        <table className="w-full text-sm">
          <caption className="sr-only">
            Recipient committees aggregated from tracked outgoing contribution records
          </caption>
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b border-slate-200 text-left">
                {hg.headers.map((header) => {
                  const meta = header.column.columnDef.meta as { className?: string } | undefined
                  const sortDirection = header.column.getIsSorted()
                  return (
                    <th
                      key={header.id}
                      aria-sort={
                        sortDirection === 'asc'
                          ? 'ascending'
                          : sortDirection === 'desc'
                            ? 'descending'
                            : undefined
                      }
                      className={`py-1 pr-4 font-medium text-slate-600 ${meta?.className ?? ''}`}
                    >
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
            {rows.map((row) => (
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
    </div>
  )
}
