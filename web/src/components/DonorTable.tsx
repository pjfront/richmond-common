'use client'

import { useId, useMemo, useState } from 'react'
import {
  availableContributionYears, contributionYear, filterHistoricalRecords,
  HISTORICAL_RECORD_LABELS, historicalRecordKind, historicalRecordSource,
} from '@/lib/historical-donor-records'
import { formatReportedMoney } from '@/lib/reported-money'
import type { DonorContribution } from '@/lib/types'
import CsvDownloadButton from '@/components/CsvDownloadButton'

const focusClass = 'min-h-11 rounded focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-civic-navy'
const inputClass = `${focusClass} border border-slate-300 bg-white px-3 py-2 text-base`

function recordDate(value: string): string {
  return contributionYear(value) ? new Date(`${value}T00:00:00Z`).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC',
  }) : 'Date not available'
}

/** A source-entry browser, not a donor ranking or a fundraising calculator. */
export default function DonorTable({ contributions }: { contributions: DonorContribution[] }) {
  const id = useId()
  const years = useMemo(() => availableContributionYears(contributions), [contributions])
  const [year, setYear] = useState<string | null>(null)
  const selectedYear = year === 'all' || (year !== null && years.includes(year)) ? year : years[0] ?? 'all'
  const [kind, setKind] = useState('all')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('date-desc')
  const [shown, setShown] = useState(20)
  const rows = useMemo(() => filterHistoricalRecords(contributions, selectedYear, kind, search)
    .map((record, index) => ({ record, index }))
    .sort((a, b) => {
      if (sort === 'amount-desc') return b.record.amount - a.record.amount || a.index - b.index
      if (sort === 'name-asc') return a.record.donor_name.localeCompare(b.record.donor_name) || a.index - b.index
      return b.record.contribution_date.localeCompare(a.record.contribution_date) || a.index - b.index
    }), [contributions, selectedYear, kind, search, sort])

  if (!contributions.length) return <p className="text-base text-slate-600">No historical finance entries available.</p>

  return <div>
    <p className="mb-4 text-base leading-relaxed text-slate-700">Browse the original entries by date and recorded type. Entries from different reports can overlap, so they are not added into a fundraising total.</p>
    <div className="mb-4 flex flex-wrap items-end gap-3">
      <label className="flex flex-col gap-1 text-sm text-slate-700" htmlFor={`${id}-year`}>Record year
        <select id={`${id}-year`} value={selectedYear} onChange={event => { setYear(event.target.value); setShown(20) }} className={inputClass}>
          <option value="all">All records</option>{years.map(value => <option key={value} value={value}>{value}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm text-slate-700" htmlFor={`${id}-kind`}>Recorded type
        <select id={`${id}-kind`} value={kind} onChange={event => { setKind(event.target.value); setShown(20) }} className={inputClass}>
          <option value="all">All types</option>{Object.entries(HISTORICAL_RECORD_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <label className="flex min-w-0 flex-1 flex-col gap-1 text-sm text-slate-700" htmlFor={`${id}-search`}>Search names, committees or filings
        <input id={`${id}-search`} type="search" value={search} onChange={event => { setSearch(event.target.value); setShown(20) }} className={`${inputClass} w-full`} />
      </label>
      <label className="flex flex-col gap-1 text-sm text-slate-700" htmlFor={`${id}-sort`}>Sort entries
        <select id={`${id}-sort`} value={sort} onChange={event => { setSort(event.target.value); setShown(20) }} className={inputClass}>
          <option value="date-desc">Newest first</option><option value="name-asc">Reported name</option><option value="amount-desc">Largest recorded amount</option>
        </select>
      </label>
    </div>
    <CsvDownloadButton filename={`council-finance-entries-${selectedYear}.csv`}
      columns={['donor_name', 'donor_employer', 'amount', 'contribution_date', 'contribution_type', 'committee_name', 'committee_fppc_id', 'filing_id', 'source', 'source_url']}
      rows={rows.map(({ record }) => ({ donor_name: record.donor_name, donor_employer: record.donor_employer,
        amount: record.amount, contribution_date: record.contribution_date, contribution_type: record.contribution_type ?? null,
        committee_name: record.committee_name ?? null, committee_fppc_id: record.committee_fppc_id ?? null,
        filing_id: record.filing_id ?? null, source: record.source, source_url: historicalRecordSource(record),
      }))} />
    <p className="my-4 text-sm text-slate-600" role="status" aria-live="polite" aria-atomic="true">
      Showing {Math.min(shown, rows.length)} of {rows.length} matching entries · {selectedYear === 'all' ? 'All records' : selectedYear}
    </p>
    <table className="block w-full text-left text-base md:table">
      <caption className="sr-only">Individual historical finance entries, with reported names, types, dates and original filings. These rows are not unique donors.</caption>
      <thead className="hidden md:table-header-group"><tr className="border-b border-slate-300">
        {['Recorded date', 'Reported name', 'Recorded type', 'Amount', 'Committee and source'].map(label => <th key={label} scope="col" className="px-2 py-3 font-medium text-slate-700">{label}</th>)}
      </tr></thead>
      <tbody className="block md:table-row-group">
        {rows.slice(0, shown).map(({ record, index }) => {
          const source = historicalRecordSource(record)
          return <tr key={index} className="mb-4 block rounded border border-slate-200 p-3 md:mb-0 md:table-row md:rounded-none md:border-x-0 md:border-t-0 md:p-0">
            <td className="block px-2 py-1 align-top md:table-cell md:py-3">{contributionYear(record.contribution_date) ? <time dateTime={record.contribution_date}>{recordDate(record.contribution_date)}</time> : recordDate(record.contribution_date)}</td>
            <td className="block break-words px-2 py-1 align-top md:table-cell md:py-3"><span className="font-medium text-slate-900">{record.donor_name}</span>
              {record.donor_employer && <p className="mt-1 text-sm text-slate-500">Reported employer: {record.donor_employer}</p>}</td>
            <td className="block px-2 py-1 align-top text-slate-600 md:table-cell md:py-3">{HISTORICAL_RECORD_LABELS[historicalRecordKind(record)]}</td>
            <td className="block px-2 py-1 align-top font-medium text-slate-900 md:table-cell md:py-3">{formatReportedMoney(Math.round(record.amount * 100))}</td>
            <td className="block break-words px-2 py-1 align-top md:table-cell md:py-3">
              <p>{record.committee_name || 'Committee not identified'}</p>
              {record.committee_fppc_id && <p className="text-sm text-slate-500">FPPC {record.committee_fppc_id}</p>}
              {source ? <a href={source} target="_blank" rel="noopener noreferrer" className={`${focusClass} inline-flex items-center text-sm text-civic-navy-light underline underline-offset-2`}>Original filing {record.filing_id}</a>
                : <p className="mt-1 text-sm text-slate-500">Original filing link unavailable.</p>}
            </td>
          </tr>
        })}
      </tbody>
    </table>
    {!rows.length && <p className="py-4 text-slate-600">No entries match these filters.</p>}
    {rows.length > shown && <button type="button" onClick={() => setShown(value => value + 20)} className={`${focusClass} inline-flex items-center px-2 text-civic-navy-light underline underline-offset-2`}>Show 20 more entries</button>}
  </div>
}
