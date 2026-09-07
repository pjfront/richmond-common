import Link from 'next/link'
import type { Metadata } from 'next'
import { getPublicFinanceSnapshot } from '@/lib/queries/finance-public'
import { filterFinanceEvents, financeEventLabel, isFinanceAdjustment } from '@/lib/finance-ledger'
import { formatCivicDate } from '@/lib/november-election'
import SuggestCorrectionLink from '@/components/SuggestCorrectionLink'
import { ANDERSON_MONEY_PATH } from '@/lib/anderson-finance'
import { JIMENEZ_MONEY_PATH } from '@/lib/jimenez-finance'

export const metadata: Metadata = {
  title: 'Who paid? Richmond campaign money and source filings',
  description: 'Search reported committee names and FPPC IDs, distinguish donations from independent spending, and read the original campaign filings.',
  alternates: { canonical: 'https://richmondcommons.org/elections/2026-general/money' },
}

const linkClass = 'inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4'
const money = (amount: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount)

export default async function MoneyLedger({ searchParams }: { searchParams: Promise<{ q?: string | string[]; committee?: string | string[]; page?: string | string[] }> }) {
  const raw = await searchParams
  const single = (value: string | string[] | undefined) => Array.isArray(value) ? value[0] : value
  const params = { q: single(raw.q), committee: single(raw.committee), page: single(raw.page) }
  const q = (params.q ?? '').slice(0, 150)
  const committee = /^\d{5,9}$/.test(params.committee ?? '') ? params.committee! : ''
  let snapshot = null
  try { snapshot = await getPublicFinanceSnapshot() } catch { /* Show a distinct error, not zero results. */ }
  const searchedWindows = [...new Map((snapshot?.coverage ?? [])
    .filter(row => row.activity_from || row.activity_through)
    .map(row => [`${row.activity_from}:${row.activity_through}`, row])).values()]
  const matches = snapshot ? filterFinanceEvents(snapshot.events, q, committee) : []
  const pageCount = Math.max(1, Math.ceil(matches.length / 25))
  const requestedPage = /^\d{1,3}$/.test(params.page ?? '') ? Number(params.page) : 1
  const page = Math.max(1, Math.min(requestedPage, pageCount))
  const shown = matches.slice((page - 1) * 25, page * 25)
  const urlParams = new URLSearchParams({ ...(q ? { q } : {}), ...(committee ? { committee } : {}) })
  function pageUrl(value: number) { const next = new URLSearchParams(urlParams); next.set('page', String(value)); return `?${next}` }
  function identity(name: string | null, id: string | null) {
    return id ? <Link className={linkClass} href={`?committee=${encodeURIComponent(id)}`}>{name ?? 'Committee'} · FPPC {id}</Link> : <span>{name ?? 'Not identified in this record'}</span>
  }
  return <article className="mx-auto max-w-4xl px-4 py-10 sm:px-6">
    <Link href="/elections/2026-general" className={linkClass}>← November guide</Link>
    <h1 className="mt-4 text-3xl font-bold text-civic-navy">Who paid? Follow the filings.</h1>
    <p className="mt-5 text-lg leading-relaxed text-slate-700">Start with the committee named in a mailer&apos;s “Paid for by” disclaimer. Search its legal name or FPPC number, then follow the reported contributions and spending.</p>
    <p className="mt-3 leading-relaxed text-slate-600">This index shows reported 2026 activity, including primary-season reports. An election is shown only when established from the source; a mention of a candidate alone does not identify the election.</p>
    {snapshot && <p className="mt-3 text-sm leading-relaxed text-slate-600">{searchedWindows.length
      ? <>Published activity windows searched: {searchedWindows.map(row => `${row.activity_from ? `from ${formatCivicDate(row.activity_from)}` : 'start not published'}${row.activity_through ? ` through ${formatCivicDate(row.activity_through)}` : '; cutoff not published'}`).join('; ')}. These are source-search windows, not the period covered by every filing.</>
      : 'A dated source-search window has not yet been published. Treat the indexed records as a partial set.'}</p>}
    <form className="mt-7 flex flex-col gap-3 sm:flex-row" action="/elections/2026-general/money" method="get">
      <div className="flex-1"><label className="block font-medium text-slate-700" htmlFor="money-search">Committee, contributor, candidate, or FPPC ID</label><input id="money-search" name="q" defaultValue={q || committee} maxLength={150} placeholder="Name printed on a mailer" className="mt-2 min-h-11 w-full rounded-md border border-slate-300 px-3 py-2 text-base" /></div>
      <button className="min-h-11 rounded-md bg-civic-navy px-5 py-2 text-white sm:self-end" type="submit">Search filings</button>
    </form>
    {committee && <p className="mt-3 text-slate-600">Showing records involving FPPC {committee}. <Link href="/elections/2026-general/money" className={linkClass}>Clear filter</Link></p>}
    {(committee === '1481105' || /\b(anderson|1481105)\b/i.test(q)) && <aside className="mt-5 rounded-lg border border-slate-200 p-5"><h2 className="text-lg font-semibold text-civic-navy">Looking for Anderson&apos;s campaign finances?</h2><p className="mt-2 leading-relaxed text-slate-700">We&apos;ve read his campaign reports and put the fundraising figures, cash balance and recent named donations together.</p><Link href={ANDERSON_MONEY_PATH} className={linkClass}>Read Anderson&apos;s campaign money summary →</Link></aside>}
    {(committee === '1488504' || /\b(jimenez|jiménez|1488504)\b/i.test(q)) && <aside className="mt-5 rounded-lg border border-slate-200 p-5"><h2 className="text-lg font-semibold text-civic-navy">Looking for Jimenez&apos;s campaign finances?</h2><p className="mt-2 leading-relaxed text-slate-700">Her campaign&apos;s reported totals include donations that do not appear individually in this index. See the dated cash balance, donation totals and later reports together.</p><Link href={JIMENEZ_MONEY_PATH} className={linkClass}>Read Jimenez&apos;s campaign money summary →</Link></aside>}
    {!snapshot ? <p role="status" className="mt-8 rounded-lg border border-amber-300 bg-amber-50 p-5">The campaign record index could not be loaded. This does not mean there were no reports. Please try again later.</p> : <>
      <div className="mt-7 flex flex-wrap items-center justify-between gap-3"><p role="status" className="text-slate-600">{matches.length} indexed {matches.length === 1 ? 'record' : 'records'}{snapshot.truncated ? ' in a limited result set' : ''} · page {page} of {pageCount}</p><a href={`/api/finance/export?${urlParams}`} className={linkClass}>Download matching records (CSV)</a></div>
      <p className="mt-2 text-sm leading-relaxed text-slate-600">Partial source coverage: records awaiting reconciliation and unprocessed paper filings may be absent. A receipt and a matching contribution-made report represent one event; a committee transfer and its later advertising expense are different events. Do not add all rows as a measure of total political spending.</p>
      {shown.length ? <ol className="mt-4 divide-y divide-slate-200">{shown.map(row => <li key={row.event_key} className="py-6">
        <div className="flex flex-wrap justify-between gap-2"><h2 className="text-lg font-semibold text-civic-navy">{financeEventLabel(row)}</h2><span className="text-xl font-semibold text-civic-navy">{money(row.amount)}</span></div>
        {isFinanceAdjustment(row) && <p className="mt-2 text-sm text-slate-600">This is a signed adjustment to the reported value. It does not by itself establish a cash refund.</p>}
        {row.event_kind === 'loan' && <p className="mt-2 text-sm text-slate-600">A reported loan value may describe a balance or activity, rather than a new loan.</p>}
        {row.event_kind === 'independent_expenditure' ? <>
          <p className="mt-3 text-slate-700">Reported spender: {identity(row.reporting_filer_name, row.reporting_filer_fppc_id)}</p>
          <p className="mt-2 text-slate-700">{row.support_oppose === 'S' ? 'Supports' : row.support_oppose === 'O' ? 'Opposes' : 'Support/opposition not established'}: {row.candidate_name ?? row.measure_name ?? 'Target not established'}</p>
        </> : <><p className="mt-3 text-slate-700">From: {identity(row.donor_name, row.donor_fppc_id)}</p><p className="mt-2 text-slate-700">To: {identity(row.recipient_name, row.recipient_fppc_id)}</p></>}
        <p className="mt-2 text-slate-600">Activity: {formatCivicDate(row.activity_date)} · {row.election_date ? `Election: ${formatCivicDate(row.election_date)}` : 'Election not established in this record'}</p>
        <p className="mt-2 text-sm text-slate-600">Official filing · retrieved {formatCivicDate(row.extracted_at)} · {row.reconciliation_status === 'matched_exact' ? 'Matching source reports linked' : 'Source-reported activity'}</p>
        <p className="mt-1 text-sm text-slate-600">Reported filing IDs: {row.filing_ids.join(', ') || 'Not available'}</p>
        <div className="mt-1 flex flex-wrap gap-x-5">{[...new Set(row.source_urls.length ? row.source_urls : [row.source_url])].map((url, index) => <a href={url} key={url} className={linkClass}>Source document {index + 1}</a>)}</div>
      </li>)}</ol> : <p className="mt-6 rounded-lg bg-slate-50 p-5">No indexed records match this search. Try the exact legal name or FPPC number from the disclaimer. Missing results are not proof that no activity occurred.</p>}
      <nav aria-label="Money ledger pages" className="mt-4 flex justify-between">{page > 1 ? <Link href={pageUrl(page - 1)} className={linkClass}>← Previous</Link> : <span />}{page < pageCount && <Link href={pageUrl(page + 1)} className={linkClass}>Next →</Link>}</nav>
    </>}
    <aside className="mt-10 rounded-lg bg-slate-50 p-6"><h2 className="text-xl font-semibold text-civic-navy">Where a money trail ends</h2><p className="mt-3 leading-relaxed text-slate-700">A committee may report money from a company, union, or nonprofit whose own funding is only partly public. Shared addresses, similar names, employment, or a common treasurer do not by themselves establish ownership or control. This view links reported committee identifiers; it does not assign corporate ownership or trace a particular donor&apos;s dollars to a particular advertisement.</p><Link href="/elections/methodology" className={linkClass}>Read the counting and identity rules →</Link></aside>
    <footer className="mt-8"><SuggestCorrectionLink /><p className="mt-3 text-sm text-slate-600">Richmond Commons. “Who paid? Follow the filings.” Data retrieval dates and source links appear with each record. Search filters are preserved in this page&apos;s URL.</p></footer>
  </article>
}
