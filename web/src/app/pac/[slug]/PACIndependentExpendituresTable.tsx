'use client'

/**
 * PACIndependentExpendituresTable. Aggregates a PAC's IE rows by
 * (candidate, direction) and presents the ledger of who they spent on
 * and against — the data layer between "PAC contributions to other
 * committees" and the underlying donor flow.
 *
 * IEs differ from contributions: the money does NOT pass through the
 * candidate's committee. The PAC pays a vendor (mailer, ad agency,
 * canvasser) directly, naming the candidate on the FPPC filing. The
 * candidate is the BENEFICIARY of the spend, not the recipient.
 */

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
import type { PACIndependentExpenditureRow } from '@/lib/types'

interface CandidateAggregate {
  candidate_name: string
  direction: 'S' | 'O' | null
  total_amount: number
  expenditure_count: number
  earliest_date: string
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

function aggregate(
  rows: PACIndependentExpenditureRow[],
): CandidateAggregate[] {
  const map = new Map<string, CandidateAggregate>()
  for (const r of rows) {
    if (!r.candidate_name) continue
    const key = `${r.candidate_name}|${r.support_or_oppose ?? ''}`
    const existing = map.get(key)
    if (existing) {
      existing.total_amount += r.amount
      existing.expenditure_count += 1
      if (r.expenditure_date > existing.latest_date)
        existing.latest_date = r.expenditure_date
      if (r.expenditure_date < existing.earliest_date)
        existing.earliest_date = r.expenditure_date
    } else {
      map.set(key, {
        candidate_name: r.candidate_name,
        direction: r.support_or_oppose,
        total_amount: r.amount,
        expenditure_count: 1,
        earliest_date: r.expenditure_date,
        latest_date: r.expenditure_date,
      })
    }
  }
  return Array.from(map.values()).sort(
    (a, b) => b.total_amount - a.total_amount,
  )
}

const columnHelper = createColumnHelper<CandidateAggregate>()

function DirectionLabel({ direction }: { direction: CandidateAggregate['direction'] }) {
  if (direction === 'S') {
    return (
      <span className="rounded border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-xs font-semibold text-emerald-700">
        Support
      </span>
    )
  }

  if (direction === 'O') {
    return (
      <span className="rounded border border-red-200 bg-red-50 px-1.5 py-0.5 text-xs font-semibold text-red-700">
        Oppose
      </span>
    )
  }

  return (
    <span className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-xs font-medium text-slate-600">
      Direction not reported
    </span>
  )
}

function makeColumns(pacUrlMap: EntityUrlMap | null) {
  return [
    columnHelper.accessor('candidate_name', {
      header: ({ column }) => (
        <CampaignEntitySortableHeader
          column={column}
          label="Candidate or beneficiary"
        />
      ),
      cell: (info) => {
        const direction = info.row.original.direction
        return (
          <div className="flex items-baseline gap-2">
            <EntityLink
              name={info.getValue()}
              urlMap={pacUrlMap}
              className="inline-flex min-h-11 items-center rounded-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-civic-navy focus:ring-offset-2"
            />
            <DirectionLabel direction={direction} />
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
    columnHelper.accessor('expenditure_count', {
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

export default function PACIndependentExpendituresTable({
  expenditures,
  pacUrlMap,
}: {
  expenditures: PACIndependentExpenditureRow[]
  pacUrlMap: EntityUrlMap | null
}) {
  const sortId = useId()
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'total_amount', desc: true },
  ])

  const aggregated = useMemo(() => aggregate(expenditures), [expenditures])
  const columns = useMemo(() => makeColumns(pacUrlMap), [pacUrlMap])
  const csvRows = useMemo(
    () =>
      expenditures.map((row) => ({
        candidate_name: row.candidate_name,
        support_or_oppose: row.support_or_oppose,
        amount: row.amount,
        expenditure_date: row.expenditure_date,
        payee_name: row.payee_name,
        description: row.description,
        expenditure_code: row.expenditure_code,
        filing_id: row.filing_id,
      })),
    [expenditures],
  )
  const unnamedRowCount = useMemo(
    () =>
      expenditures.reduce(
        (count, row) => count + (row.candidate_name ? 0 : 1),
        0,
      ),
    [expenditures],
  )

  const table = useReactTable({
    data: aggregated,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  if (expenditures.length === 0) {
    return (
      <p className="text-sm text-slate-500 italic">
        No independent expenditures tracked.
      </p>
    )
  }

  const rows = table.getRowModel().rows

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-600">
          {expenditures.length.toLocaleString()} filing row
          {expenditures.length === 1 ? '' : 's'} &middot;{' '}
          {aggregated.length.toLocaleString()} named candidate group
          {aggregated.length === 1 ? '' : 's'}
          {unnamedRowCount > 0
            ? ` · ${unnamedRowCount.toLocaleString()} without a named candidate (CSV only)`
            : ''}
        </p>
        <CsvDownloadButton
          filename="richmond-committee-independent-expenditure-filing-records.csv"
          columns={[
            'candidate_name',
            'support_or_oppose',
            'amount',
            'expenditure_date',
            'payee_name',
            'description',
            'expenditure_code',
            'filing_id',
          ]}
          rows={csvRows}
        />
      </div>

      {aggregated.length > 0 ? (
        <>
          <div className="mb-3 md:hidden">
            <label
              htmlFor={sortId}
              className="mb-1 block text-sm font-medium text-slate-700"
            >
              Sort independent expenditure records
            </label>
            <select
              id={sortId}
              value={sorting[0]?.id ?? 'total_amount'}
              onChange={(event) => {
                const id = event.target.value
                setSorting([{ id, desc: id !== 'candidate_name' }])
              }}
              className="min-h-11 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-base focus:border-civic-navy focus:outline-none focus:ring-2 focus:ring-civic-navy/30"
            >
              <option value="total_amount">Reported total</option>
              <option value="candidate_name">Candidate or beneficiary</option>
              <option value="expenditure_count">Number of records</option>
              <option value="latest_date">Latest filing date</option>
            </select>
          </div>

          <ul
            className="space-y-3 md:hidden"
            aria-label="Independent expenditure filing totals"
          >
            {rows.map((row) => {
              const expenditure = row.original
              return (
                <li
                  key={row.id}
                  className="rounded-md border border-slate-200 p-4 text-sm"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium text-slate-900">
                      <EntityLink
                        name={expenditure.candidate_name}
                        urlMap={pacUrlMap}
                        className="inline-flex min-h-11 items-center rounded-sm focus:outline-none focus:ring-2 focus:ring-civic-navy focus:ring-offset-2"
                      />
                    </p>
                    <DirectionLabel direction={expenditure.direction} />
                  </div>
                  <p className="mt-2 text-slate-700">
                    {fmt(expenditure.total_amount)} across{' '}
                    {expenditure.expenditure_count} record
                    {expenditure.expenditure_count === 1 ? '' : 's'} &middot;{' '}
                    {fmtDateRange(
                      expenditure.earliest_date,
                      expenditure.latest_date,
                    )}
                  </p>
                </li>
              )
            })}
          </ul>

          <div className="hidden md:block">
            <table className="w-full text-sm">
              <caption className="sr-only">
                Independent expenditures aggregated by named candidate and
                reported direction
              </caption>
              <thead>
                {table.getHeaderGroups().map((hg) => (
                  <tr
                    key={hg.id}
                    className="border-b border-slate-200 text-left"
                  >
                    {hg.headers.map((header) => {
                      const meta = header.column.columnDef.meta as
                        | { className?: string }
                        | undefined
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
                            : flexRender(
                                header.column.columnDef.header,
                                header.getContext(),
                              )}
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
                      const meta = cell.column.columnDef.meta as
                        | { className?: string }
                        | undefined
                      return (
                        <td
                          key={cell.id}
                          className={`py-2 pr-4 ${meta?.className ?? ''}`}
                        >
                          {flexRender(
                            cell.column.columnDef.cell,
                            cell.getContext(),
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <p className="rounded-md border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
          The tracked filings do not name a candidate or beneficiary. Download
          the CSV to review the available filing rows.
        </p>
      )}
    </div>
  )
}
