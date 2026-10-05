import Link from 'next/link'
import type { Metadata } from 'next'
import { getPublicFinanceSnapshot } from '@/lib/queries/finance-public'
import type { PublicFinanceSnapshot } from '@/lib/queries/finance-public'
import { FINANCE_ACTIVITIES, filterFinanceEvents, financeEventLabel, financeFilterParams, isFinanceAdjustment, parseFinanceFilters } from '@/lib/finance-ledger'
import { formatCivicDate } from '@/lib/november-election'
import FinanceCommitteeContext from '@/components/civic/FinanceCommitteeContext'
import FinanceCoverageNote from '@/components/civic/FinanceCoverageNote'
import organizations from '@/data/committee-organization-filings.json'

export const metadata: Metadata = {
  title: 'Campaign money',
  description: 'Look up reported Richmond campaign contributions and spending, with original filings and source coverage.',
}

const linkClass = 'inline-flex min-h-11 items-center break-words text-civic-navy underline underline-offset-4'
const formatMoney = (amount: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount)
const PAGE_SIZE = 25

export default async function MoneyPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const raw = await searchParams
  const single = (value: string | string[] | undefined) => Array.isArray(value) ? value[0] : value
  const params = Object.fromEntries(Object.entries(raw).map(([key, value]) => [key, single(value)]))
  const filters = parseFinanceFilters(params)
  const { q, committee, activity, role } = filters
  let snapshot: PublicFinanceSnapshot | null = null
  try {
    snapshot = await getPublicFinanceSnapshot()
  } catch {
    // A failed read must remain unavailable, rather than becoming zero activity.
  }
  const matches = snapshot ? filterFinanceEvents(snapshot.events, filters) : []
  const pageCount = Math.max(1, Math.ceil(matches.length / PAGE_SIZE))
  const focusedEvent = (params.event ?? '').slice(0, 512)
  const focusedIndex = focusedEvent ? matches.findIndex(row => row.event_key === focusedEvent) : -1
  const requestedPage = /^\d{1,3}$/.test(params.page ?? '')
    ? Number(params.page)
    : focusedIndex >= 0 ? Math.floor(focusedIndex / PAGE_SIZE) + 1 : 1
  const page = Math.max(1, Math.min(requestedPage, pageCount))
  const shown = matches.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  const urlParams = financeFilterParams(filters)

  function pageUrl(value: number) {
    const next = new URLSearchParams(urlParams)
    next.set('page', String(value))
    return `/money?${next}#records`
  }

  function identity(name: string | null, id: string | null) {
    const label = organizations.committees.find(row => row.fppc_id === id)?.display_name ?? name
    return id
      ? <Link className={linkClass} href={`/money?committee=${encodeURIComponent(id)}#records`} title={name ?? undefined}>{label ?? 'Committee'} · FPPC {id}</Link>
      : <span className="break-words">{name ?? 'Not identified in this record'}</span>
  }

  return (
    <article className="mx-auto max-w-5xl px-4 py-10 sm:px-6 lg:px-8">
      <h1 className="text-3xl font-bold tracking-tight text-civic-navy sm:text-4xl">Campaign money</h1>
      <p className="mt-4 max-w-3xl text-lg leading-relaxed text-slate-700">Look up a contributor, committee, or candidate. Follow the reported contributions and spending back to the original filings.</p>
      <p className="mt-3 max-w-3xl leading-relaxed text-slate-600">This partial index covers reported 2026 activity. A campaign&apos;s fundraising total comes from its dated reports; adding these records together does not establish that total.</p>

      <form key={urlParams.toString()} action="/money#records" method="get" className="mt-7 rounded-xl border border-slate-200 bg-white p-4 sm:p-6">
        {committee && <input type="hidden" name="committee" value={committee} />}
        <label htmlFor="money-search" className="block font-semibold text-civic-navy">{committee ? 'Search within this committee’s records' : 'Contributor, committee, candidate, or FPPC number'}</label>
        <input id="money-search" type="search" name="q" defaultValue={q} maxLength={150} placeholder="Name printed on a mailer, or a contributor’s name" className="mt-2 min-h-12 w-full rounded-md border border-slate-500 px-3 text-base focus:outline-2 focus:outline-offset-2 focus:outline-civic-navy" />
        <div className="mt-4 flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-end">
          <div className="min-w-0 flex-1">
            <label htmlFor="money-activity" className="block font-medium text-slate-700">Kind of activity</label>
            <select id="money-activity" name="activity" defaultValue={activity} className="mt-2 min-h-11 w-full rounded-md border border-slate-500 bg-white px-3 text-base focus:outline-2 focus:outline-offset-2 focus:outline-civic-navy">
              {FINANCE_ACTIVITIES.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </div>
          {committee && <div className="min-w-0 flex-1">
            <label htmlFor="money-role" className="block font-medium text-slate-700">This committee</label>
            <select id="money-role" name="role" defaultValue={role} className="mt-2 min-h-11 w-full rounded-md border border-slate-500 bg-white px-3 text-base focus:outline-2 focus:outline-offset-2 focus:outline-civic-navy">
              <option value="">All records involving it</option>
              <option value="recipient">Recipient or borrower</option>
              <option value="source">Contributor, lender, or spender</option>
            </select>
          </div>}
          <button type="submit" className="min-h-11 rounded-md bg-civic-navy px-5 font-medium text-white hover:bg-civic-navy-light">Search filings</button>
        </div>
      </form>

      {committee && <p className="mt-3 leading-relaxed text-slate-600">Showing records involving FPPC {committee}. <Link href="/money" className={linkClass}>Clear committee filter</Link></p>}
      <FinanceCommitteeContext committee={committee} />

      {!snapshot ? (
        <div role="alert" className="mt-8 rounded-lg border border-amber-300 bg-amber-50 p-5">
          <h2 className="font-semibold text-civic-navy">Campaign records are temporarily unavailable</h2>
          <p className="mt-2 leading-relaxed text-slate-700">The index could not be loaded. This does not mean there were no reports. Try this page again later.</p>
        </div>
      ) : (
        <section aria-labelledby="records-heading" className="mt-8">
          <div id="records" className="scroll-mt-6 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 id="records-heading" className="text-xl font-semibold text-civic-navy">Reported records</h2>
              <p role="status" className="mt-2 leading-relaxed text-slate-600">{matches.length} indexed {matches.length === 1 ? 'record' : 'records'}{snapshot.truncated ? ' within the limited result set' : ''} · page {page} of {pageCount}</p>
            </div>
            <a href={`/api/finance/export?${urlParams}`} className={linkClass}>Download matching records (CSV)</a>
          </div>
          <FinanceCoverageNote coverage={snapshot.coverage} />
          {focusedEvent && focusedIndex < 0 && <p role="status" className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-4 leading-relaxed text-slate-700">The linked record is not present in this view of the current index. Check the search filters and original source. This does not establish that the reported activity did not occur.</p>}
          <p className="mt-4 leading-relaxed text-slate-600">A contribution and a later advertising expense are different steps in a money trail. Loans, noncash contributions, and signed adjustments retain their separate meanings. Possible repetitions or conflicts may still await review.</p>
          {shown.length ? <ol className="mt-5 space-y-4">
            {shown.map(row => <li key={row.event_key} id={row.event_key} className="scroll-mt-6 rounded-lg border border-slate-200 bg-white p-5 sm:p-6">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <h3 className="text-lg font-semibold text-civic-navy">{financeEventLabel(row)}</h3>
                <p className="text-xl font-semibold text-civic-navy">{formatMoney(row.amount)}</p>
              </div>
              {isFinanceAdjustment(row) && <p className="mt-3 leading-relaxed text-slate-600">This is a signed adjustment to the reported value. It does not by itself establish a cash refund.</p>}
              {row.event_kind === 'loan' && <p className="mt-3 leading-relaxed text-slate-600">A reported loan value may describe a balance or activity, rather than a new loan.</p>}
              {row.event_kind === 'independent_expenditure' ? <>
                <p className="mt-3 leading-relaxed text-slate-700">Reported spender: {identity(row.reporting_filer_name, row.reporting_filer_fppc_id)}</p>
                <p className="mt-2 leading-relaxed text-slate-700">{row.support_oppose === 'S' ? 'Supports' : row.support_oppose === 'O' ? 'Opposes' : 'Support/opposition not established'}: {row.candidate_name ?? row.measure_name ?? 'Target not established'}</p>
              </> : <>
                <p className="mt-3 leading-relaxed text-slate-700">From: {identity(row.donor_name, row.donor_fppc_id)}</p>
                <p className="mt-2 leading-relaxed text-slate-700">To: {identity(row.recipient_name, row.recipient_fppc_id)}</p>
              </>}
              <p className="mt-3 leading-relaxed text-slate-600">Activity: {formatCivicDate(row.activity_date)} · {row.election_date ? `Election: ${formatCivicDate(row.election_date)}` : 'Election not established in this record'}</p>
              <div className="mt-4 border-t border-slate-200 pt-3">
                <p className="text-base leading-relaxed text-slate-600">Source tier {row.source_tier} · official filing · retrieved {formatCivicDate(row.extracted_at)} · {row.reconciliation_status === 'matched_exact' ? 'Matching source reports linked' : 'Source-reported activity'}</p>
                <p className="mt-1 break-words text-base leading-relaxed text-slate-600">Reported filing IDs: {row.filing_ids.join(', ') || 'Not available'}</p>
                <div className="mt-1 flex flex-wrap gap-x-5">{[...new Set(row.source_urls.length ? row.source_urls : [row.source_url])].map((url, index) => <a href={url} key={url} className={linkClass}>Source document {index + 1}</a>)}</div>
              </div>
            </li>)}
          </ol> : <p className="mt-6 rounded-lg border border-slate-200 bg-white p-5 leading-relaxed text-slate-700">No indexed records match these filters. Try an exact legal name or FPPC number from a source filing. Missing results do not establish that no activity occurred.</p>}
          <nav aria-label="Money records pages" className="mt-5 flex justify-between gap-4">
            {page > 1 ? <Link href={pageUrl(page - 1)} className={linkClass}>← Previous</Link> : <span />}
            {page < pageCount ? <Link href={pageUrl(page + 1)} className={linkClass}>Next →</Link> : null}
          </nav>
        </section>
      )}

      <aside aria-labelledby="money-context-heading" className="mt-10 rounded-lg border border-slate-200 p-5 sm:p-6">
        <h2 id="money-context-heading" className="text-xl font-semibold text-civic-navy">What a money trail can establish</h2>
        <p className="mt-3 leading-relaxed text-slate-700">These records show reported financial activity. Similar names, shared addresses, employment, or a common treasurer do not by themselves establish ownership or control. A donation and a vote do not establish why a council member voted.</p>
        <Link href="/elections/methodology" className={`${linkClass} mt-2`}>Read the counting and identity rules →</Link>
      </aside>
      <p className="mt-6 text-base leading-relaxed text-slate-600">Richmond Commons. “Campaign money.” Source retrieval dates appear with each record. Search filters remain in this page&apos;s link.</p>
    </article>
  )
}
