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
import type { PACContributionRow } from '@/lib/types'

interface DonorAggregate {
  donor_name: string
  donor_employer: string | null
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

interface DonorAggregateInternal extends DonorAggregate {
  earliest_date: string
}

function aggregate(rows: PACContributionRow[]): DonorAggregateInternal[] {
  const map = new Map<string, DonorAggregateInternal>()
  for (const r of rows) {
    const existing = map.get(r.donor_name)
    if (existing) {
      existing.total_amount += r.amount
      existing.contribution_count += 1
      if (r.contribution_date > existing.latest_date) existing.latest_date = r.contribution_date
      if (r.contribution_date < existing.earliest_date) existing.earliest_date = r.contribution_date
    } else {
      map.set(r.donor_name, {
        donor_name: r.donor_name,
        donor_employer: r.donor_employer,
        total_amount: r.amount,
        contribution_count: 1,
        latest_date: r.contribution_date,
        earliest_date: r.contribution_date,
      })
    }
  }
  return Array.from(map.values()).sort((a, b) => b.total_amount - a.total_amount)
}

function fmtDateRange(earliest: string, latest: string): string {
  if (earliest === latest) {
    return new Date(earliest + 'T00:00:00').toLocaleDateString('en-US', {
      month: 'short',
      year: 'numeric',
    })
  }
  const e = new Date(earliest + 'T00:00:00')
  const l = new Date(latest + 'T00:00:00')
  const sameYear = e.getFullYear() === l.getFullYear()
  const eFmt = sameYear
    ? e.toLocaleDateString('en-US', { month: 'short' })
    : e.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
  const lFmt = l.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
  return `${eFmt} – ${lFmt}`
}

const columnHelper = createColumnHelper<DonorAggregateInternal>()

function makeColumns(pacUrlMap: EntityUrlMap | null) {
  return [
    columnHelper.accessor('donor_name', {
      header: ({ column }) => (
        <CampaignEntitySortableHeader column={column} label="Donor" />
      ),
      cell: (info) => (
        <EntityLink
          name={info.getValue()}
          urlMap={pacUrlMap}
          className="inline-flex min-h-11 items-center rounded-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-civic-navy focus:ring-offset-2"
        />
      ),
    }),
    columnHelper.accessor('donor_employer', {
      header: 'Employer',
      cell: (info) => info.getValue() ?? '·',
      enableSorting: false,
      meta: { className: 'hidden sm:table-cell text-slate-500' },
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
          label="Filing dates"
          className="justify-end"
        />
      ),
      cell: (info) => {
        const row = info.row.original
        return (
          <span className="text-slate-500 tabular-nums whitespace-nowrap">
            {fmtDateRange(row.earliest_date, row.latest_date)}
          </span>
        )
      },
      meta: { className: 'text-right hidden md:table-cell' },
    }),
  ]
}

export default function PACDonorTable({
  contributions,
  pacUrlMap,
}: {
  contributions: PACContributionRow[]
  pacUrlMap: EntityUrlMap | null
}) {
  const searchId = useId()
  const sortId = useId()
  const [search, setSearch] = useState('')
  const [showAll, setShowAll] = useState(false)
  const [sorting, setSorting] = useState<SortingState>([{ id: 'total_amount', desc: true }])

  const aggregated = useMemo(() => aggregate(contributions), [contributions])
  const columns = useMemo(() => makeColumns(pacUrlMap), [pacUrlMap])
  const csvRows = useMemo(
    () =>
      contributions.map((row) => ({
        donor_name: row.donor_name,
        donor_employer: row.donor_employer,
        amount: row.amount,
        contribution_date: row.contribution_date,
        contribution_type: row.contribution_type,
        filing_id: row.filing_id,
      })),
    [contributions],
  )

  const filtered = useMemo(() => {
    if (!search.trim()) return aggregated
    const q = search.toLowerCase()
    return aggregated.filter(
      (d) => d.donor_name.toLowerCase().includes(q) || (d.donor_employer ?? '').toLowerCase().includes(q),
    )
  }, [aggregated, search])

  const table = useReactTable({
    data: filtered,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  if (aggregated.length === 0) {
    return <p className="text-sm text-slate-500 italic">No contribution data available.</p>
  }

  const allRows = table.getRowModel().rows
  const visibleRows = showAll ? allRows : allRows.slice(0, 25)

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div className="w-full sm:w-72">
          <label htmlFor={searchId} className="mb-1 block text-sm font-medium text-slate-700">
            Search donors
          </label>
          <input
            id={searchId}
            type="search"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value)
              setShowAll(false)
            }}
            placeholder="Name or employer"
            className="min-h-11 w-full rounded-md border border-slate-300 px-3 py-2 text-base focus:border-civic-navy focus:outline-none focus:ring-2 focus:ring-civic-navy/30"
          />
        </div>
        <CsvDownloadButton
          filename="richmond-committee-donor-filing-records.csv"
          columns={[
            'donor_name',
            'donor_employer',
            'amount',
            'contribution_date',
            'contribution_type',
            'filing_id',
          ]}
          rows={csvRows}
        />
      </div>

      <p role="status" aria-live="polite" className="text-sm text-slate-500 mb-3">
        {filtered.length} of {aggregated.length} named donor
        {aggregated.length !== 1 ? 's' : ''}
      </p>

      <div className="mb-3 md:hidden">
        <label htmlFor={sortId} className="mb-1 block text-sm font-medium text-slate-700">
          Sort donor records
        </label>
        <select
          id={sortId}
          value={sorting[0]?.id ?? 'total_amount'}
          onChange={(event) => {
            const id = event.target.value
            setSorting([{ id, desc: id !== 'donor_name' }])
          }}
          className="min-h-11 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-base focus:border-civic-navy focus:outline-none focus:ring-2 focus:ring-civic-navy/30"
        >
          <option value="total_amount">Reported total</option>
          <option value="donor_name">Donor name</option>
          <option value="contribution_count">Number of records</option>
          <option value="latest_date">Latest filing date</option>
        </select>
      </div>

      <ul className="space-y-3 md:hidden" aria-label="Named donor filing totals">
        {visibleRows.map((row) => {
          const donor = row.original
          return (
            <li key={row.id} className="rounded-md border border-slate-200 p-4 text-sm">
              <p className="font-medium text-slate-900">
                <EntityLink
                  name={donor.donor_name}
                  urlMap={pacUrlMap}
                  className="inline-flex min-h-11 items-center rounded-sm focus:outline-none focus:ring-2 focus:ring-civic-navy focus:ring-offset-2"
                />
              </p>
              {donor.donor_employer ? (
                <p className="mt-1 text-slate-600">Employer: {donor.donor_employer}</p>
              ) : null}
              <p className="mt-2 text-slate-700">
                {fmt(donor.total_amount)} across {donor.contribution_count}{' '}
                record{donor.contribution_count === 1 ? '' : 's'} &middot;{' '}
                {fmtDateRange(donor.earliest_date, donor.latest_date)}
              </p>
            </li>
          )
        })}
      </ul>

      <div className="hidden md:block">
        <table className="w-full text-sm">
          <caption className="sr-only">
            Named donors aggregated from tracked committee contribution records
          </caption>
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b border-slate-200 text-left">
                {hg.headers.map((header) => {
                  const meta = header.column.columnDef.meta as { className?: string } | undefined
                  return (
                    <th
                      key={header.id}
                      aria-sort={
                        header.column.getCanSort()
                          ? header.column.getIsSorted() === 'asc'
                            ? 'ascending'
                            : header.column.getIsSorted() === 'desc'
                              ? 'descending'
                              : 'none'
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
            {visibleRows.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-6 text-center text-sm text-slate-400 italic">
                  No donors match this search.
                </td>
              </tr>
            ) : (
              visibleRows.map((row) => (
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
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
        {!showAll && allRows.length > 25 && (
          <button
            onClick={() => setShowAll(true)}
            className="inline-flex min-h-11 items-center rounded-sm text-sm font-medium text-civic-navy-light hover:text-civic-navy focus:outline-none focus:ring-2 focus:ring-civic-navy focus:ring-offset-2"
          >
            Show all {allRows.length} donors
          </button>
        )}
      </div>
    </div>
  )
}
