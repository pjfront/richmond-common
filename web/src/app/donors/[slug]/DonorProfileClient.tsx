'use client'

import { useId, useMemo, useState } from 'react'
import CsvDownloadButton from '@/components/CsvDownloadButton'
import type { DonorOutgoingRow } from '@/lib/types'
import { contributionYear, historicalRecordKind, HISTORICAL_RECORD_LABELS } from '@/lib/historical-donor-records'

const money = (amount: number) => amount.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 })

export default function DonorProfileClient({ outgoing, donorDisplay }: { outgoing: DonorOutgoingRow[]; donorDisplay: string }) {
  const id = useId()
  const [year, setYear] = useState('all')
  const [search, setSearch] = useState('')
  const [order, setOrder] = useState('newest')
  const [shown, setShown] = useState(20)
  const years = useMemo(() => [...new Set(outgoing.map(row => contributionYear(row.contribution_date)).filter((value): value is string => value !== null))].sort().reverse(), [outgoing])
  const rows = useMemo(() => outgoing.filter(row => (year === 'all' || contributionYear(row.contribution_date) === year)
    && `${row.recipient_committee_name} ${row.recipient_candidate_name ?? ''}`.toLowerCase().includes(search.trim().toLowerCase()))
    .sort((a, b) => (order === 'amount' ? b.amount - a.amount : b.contribution_date.localeCompare(a.contribution_date)) || a.record_id.localeCompare(b.record_id)), [outgoing, year, search, order])
  const csvRows = useMemo(() => rows.map(row => ({ ...row })), [rows])
  return <section aria-label={`Historical entries for ${donorDisplay}`}>
    <div className="mb-4 flex flex-wrap items-end gap-4">
      <label className="grid gap-1 text-sm text-slate-700" htmlFor={`${id}-year`}>Record year
        <select id={`${id}-year`} value={year} onChange={event => { setYear(event.target.value); setShown(20) }} className="min-h-11 rounded border border-slate-300 bg-white px-3 text-base"><option value="all">All recorded years</option>{years.map(value => <option key={value}>{value}</option>)}</select>
      </label>
      <label className="grid min-w-0 flex-1 gap-1 text-sm text-slate-700" htmlFor={`${id}-search`}>Search receiving committees
        <input id={`${id}-search`} type="search" value={search} onChange={event => { setSearch(event.target.value); setShown(20) }} className="min-h-11 min-w-0 rounded border border-slate-300 px-3 text-base" />
      </label>
      <label className="grid gap-1 text-sm text-slate-700" htmlFor={`${id}-order`}>Sort entries
        <select id={`${id}-order`} value={order} onChange={event => { setOrder(event.target.value); setShown(20) }} className="min-h-11 rounded border border-slate-300 bg-white px-3 text-base"><option value="newest">Newest first</option><option value="amount">Largest reported amount</option></select>
      </label>
    </div>
    <CsvDownloadButton filename="historical-donor-records.csv" columns={['record_id', 'amount', 'contribution_date', 'contribution_type', 'recipient_committee_name', 'recipient_committee_fppc_id', 'filing_id', 'source', 'source_url']} rows={csvRows} />
    <p role="status" aria-live="polite" aria-atomic="true" className="my-4 text-sm text-slate-600">Showing {Math.min(shown, rows.length)} of {rows.length} matching filing entr{rows.length === 1 ? 'y' : 'ies'}</p>
    <ul id={`${id}-entries`} className="divide-y divide-slate-200">
      {rows.slice(0, shown).map(row => <li key={row.record_id} className="py-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2"><p className="font-medium text-slate-900">{row.recipient_committee_name}</p><p className="font-semibold text-civic-navy">{money(row.amount)}</p></div>
        <p className="mt-1 text-sm text-slate-600"><time dateTime={row.contribution_date}>{row.contribution_date}</time> · {HISTORICAL_RECORD_LABELS[historicalRecordKind(row)]}</p>
        {row.recipient_committee_fppc_id && <p className="mt-1 text-sm text-slate-600">Committee FPPC {row.recipient_committee_fppc_id}</p>}
        {row.source_url ? <a href={row.source_url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-flex min-h-11 items-center text-sm text-civic-navy underline">Original filing {row.filing_id}</a> : <p className="mt-2 text-sm text-slate-600">This imported record has no original filing link.</p>}
      </li>)}
    </ul>
    {rows.length > shown && <button type="button" aria-controls={`${id}-entries`} onClick={() => setShown(value => value + 20)}
      className="mt-3 inline-flex min-h-11 items-center rounded px-2 text-civic-navy underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-civic-navy">
      Show {Math.min(20, rows.length - shown)} more entries
    </button>}
  </section>
}
