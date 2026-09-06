'use client'

import { useState, useMemo, useId } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
  type Column,
} from '@tanstack/react-table'
import {
  aggregateDonorRecords, availableContributionYears, contributionDateRange,
  contributionsInYear, donorRecordSources, searchDonorRecords, sumRecordedAmounts,
} from '@/lib/historical-donor-records'
import type { DonorAggregate, DonorContribution } from '@/lib/types'

// ── Helpers ──────────────────────────────────────────────────

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: Number.isInteger(amount) ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(amount)
}

function formatRecordDate(date: string): string {
  return new Date(`${date}T00:00:00Z`).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC',
  })
}

// ── Table Columns ────────────────────────────────────────────

function RecordSortHeader<T>({ column, label }: { column: Column<T, unknown>; label: string }) {
  const sorted = column.getIsSorted()
  return (
    <button type="button" onClick={column.getToggleSortingHandler()}
      className="inline-flex min-h-11 items-center gap-1 rounded text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-civic-navy">
      {label}<span aria-hidden="true">{sorted === 'asc' ? '↑' : sorted === 'desc' ? '↓' : '↕'}</span>
    </button>
  )
}

const columnHelper = createColumnHelper<DonorAggregate>()

const columns = [
  columnHelper.accessor('donor_name', {
    header: ({ column }) => <RecordSortHeader column={column} label="Donor" />,
    cell: (info) => (
      <span className="text-slate-900">
        {info.getValue()}
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
    header: ({ column }) => <RecordSortHeader column={column} label="Amount" />,
    cell: (info) => (
      <span className="font-medium text-slate-900">{formatCurrency(info.getValue())}</span>
    ),
    meta: { className: 'text-right' },
  }),
  columnHelper.accessor('contribution_count', {
    header: ({ column }) => <RecordSortHeader column={column} label="Records" />,
    cell: (info) => <span className="text-slate-500">{info.getValue()}</span>,
    meta: { className: 'text-right' },
  }),
]

// ── Main Component ───────────────────────────────────────────

const NETFILE_PUBLIC_URL = 'https://public.netfile.com/pub2/?AID=RICH'

interface DonorTableProps {
  contributions: DonorContribution[]
}

export default function DonorTable({ contributions }: DonorTableProps) {
  const searchId = useId()
  const years = useMemo(() => availableContributionYears(contributions), [contributions])
  const [selectedYear, setSelectedYear] = useState<string | null>(null)
  const activeYear = selectedYear === 'all' || (selectedYear !== null && years.includes(selectedYear))
    ? selectedYear : years[0] ?? 'all'
  const [sorting, setSorting] = useState<SortingState>([{ id: 'total_amount', desc: true }])
  const [showAll, setShowAll] = useState(false)
  const [search, setSearch] = useState('')

  const records = useMemo(() => contributionsInYear(contributions, activeYear), [contributions, activeYear])
  const donors = useMemo(() => aggregateDonorRecords(records), [records])
  const filtered = useMemo(() => searchDonorRecords(donors, search), [donors, search])
  const matchingRecords = useMemo(() => {
    const names = new Set(filtered.map(donor => donor.donor_name))
    return records.filter(record => names.has(record.donor_name))
  }, [records, filtered])
  const dateRange = useMemo(() => contributionDateRange(matchingRecords), [matchingRecords])
  const sources = useMemo(() => donorRecordSources(matchingRecords), [matchingRecords])
  const recordedAmount = sumRecordedAmounts(filtered.map(donor => donor.total_amount))
  const recordCount = filtered.reduce((sum, donor) => sum + donor.contribution_count, 0)

  const table = useReactTable({
    data: filtered,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  if (contributions.length === 0) {
    return <p className="text-sm text-slate-500 italic">No historical donation records available.</p>
  }

  const allRows = table.getRowModel().rows
  const visibleRows = showAll ? allRows : allRows.slice(0, 10)

  return (
    <div>
      <p className="mb-4 text-sm text-slate-600">
        These donation records come from linked committees and may not include all fundraising. Years refer to donation dates.
      </p>
      <div className="mb-4 flex flex-wrap items-end gap-4">
        {years.length > 0 && (
          <div role="group" aria-label="Contribution year" className="flex flex-wrap gap-1.5">
            {['all', ...years].map(year => (
              <button
                type="button"
                key={year}
                aria-pressed={activeYear === year}
                onClick={() => { setSelectedYear(year); setShowAll(false) }}
                className={`min-h-11 rounded-md border px-3 py-2 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-civic-navy ${
                  activeYear === year ? 'border-civic-navy bg-civic-navy text-white' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                }`}
              >
                {year === 'all' ? 'All records' : year}
              </button>
            ))}
          </div>
        )}
        <div className="w-full sm:w-72">
          <label htmlFor={searchId} className="mb-1 block text-xs font-medium text-slate-600">Search donors or employers</label>
          <input
            id={searchId}
            type="search"
            value={search}
            onChange={event => { setSearch(event.target.value); setShowAll(false) }}
            className="min-h-11 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-civic-navy/40"
          />
        </div>
      </div>

      <div className="mb-3" role="status" aria-live="polite" aria-atomic="true">
        <p className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-lg font-semibold text-civic-navy">{formatCurrency(recordedAmount)}</span>
          <span className="text-sm text-slate-600">
            in {recordCount} {search.trim() ? 'matching ' : ''}donation record{recordCount !== 1 ? 's' : ''}
            {' · '}{activeYear === 'all' ? 'All records' : activeYear}
          </span>
        </p>
        {dateRange && (
          <p className="mt-1 text-xs text-slate-500">
            Dates of these records: <time dateTime={dateRange.first}>{formatRecordDate(dateRange.first)}</time>
            {dateRange.first !== dateRange.last && <> to <time dateTime={dateRange.last}>{formatRecordDate(dateRange.last)}</time></>}
          </p>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">Historical donation records grouped by reported donor name, {activeYear === 'all' ? 'all recorded years' : activeYear}</caption>
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="border-b border-slate-200 text-left">
                {headerGroup.headers.map((header) => {
                  const meta = header.column.columnDef.meta as { className?: string } | undefined
                  return (
                    <th key={header.id} scope="col" aria-sort={header.column.getIsSorted() === 'asc' ? 'ascending' : header.column.getIsSorted() === 'desc' ? 'descending' : undefined} className={`py-2 pr-4 font-medium text-slate-600 ${meta?.className ?? ''}`}>
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
                <td colSpan={4} className="py-6 text-center text-sm text-slate-400 italic">
                  {search.trim() ? 'No donors or employers match this search.' : 'No historical donation records in this period.'}
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

      {/* Show all / search result count */}
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
        {!showAll && allRows.length > 10 && (
          <button
            type="button"
            onClick={() => setShowAll(true)}
            className="inline-flex min-h-11 items-center rounded text-sm text-civic-navy-light hover:text-civic-navy focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-civic-navy"
          >
            Show all {allRows.length} donor rows
          </button>
        )}
        {search.trim() && (
          <span className="text-xs text-slate-400">
            {filtered.length} of {donors.length} donor rows match
          </span>
        )}
      </div>

      {sources.length > 0 && (
        <details className="mt-4 rounded-md border border-slate-200 p-3">
          <summary className="min-h-11 cursor-pointer rounded text-sm font-medium text-civic-navy focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-civic-navy">
            Committees and source reports for these records ({sources.length})
          </summary>
          <ul className="mt-3 divide-y divide-slate-100">
            {sources.map(source => (
              <li key={source.key} className="py-3 first:pt-0 last:pb-0">
                <p className="text-sm font-medium text-slate-800">{source.committeeName}</p>
                {source.committeeFppcId && <p className="text-xs text-slate-500">FPPC {source.committeeFppcId}</p>}
                <p className="mt-1 text-xs text-slate-600">
                  {source.recordCount} donation record{source.recordCount !== 1 ? 's' : ''} · {formatCurrency(source.recordedAmount)} recorded
                  {source.dateRange && <>{' · '}<time dateTime={source.dateRange.first}>{formatRecordDate(source.dateRange.first)}</time>
                    {source.dateRange.first !== source.dateRange.last && <> to <time dateTime={source.dateRange.last}>{formatRecordDate(source.dateRange.last)}</time></>}
                  </>}
                </p>
                {source.recordTypes.length > 0 && <p className="mt-1 text-xs text-slate-500">Record types: {source.recordTypes.map(type => type.replaceAll('_', ' ')).join(', ')}</p>}
                {source.sourceUrl ? (
                  <a href={source.sourceUrl} target="_blank" rel="noopener noreferrer" className="mt-1 inline-flex min-h-11 items-center rounded text-sm text-civic-navy-light underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-civic-navy">
                    Original filing {source.filingId}
                  </a>
                ) : <p className="mt-1 text-xs text-slate-500">Original filing link unavailable in these records.</p>}
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="mt-4 pt-3 border-t border-slate-100 flex justify-end">
        <a
          href={NETFILE_PUBLIC_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex min-h-11 items-center rounded text-xs text-slate-500 hover:text-civic-navy-light focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-civic-navy"
        >
          View all filings on NetFile &rarr;
        </a>
      </div>
    </div>
  )
}
