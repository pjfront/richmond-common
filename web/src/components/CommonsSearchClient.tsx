'use client'

import { useEffect, useRef, useState, type FormEvent } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { commonsSearchParams, planCommonsSearch } from '@/lib/commons-search'
import type { CommonsAgendaRecord, CommonsMode, CommonsMoneyRecord, CommonsSearchFilters, CommonsSearchResponse } from '@/lib/commons-search'
import { financeEventLabel, isFinanceAdjustment } from '@/lib/finance-ledger'
import { formatCivicDate } from '@/lib/november-election'
import FinanceCoverageNote from './civic/FinanceCoverageNote'
import VoteSourceReviewNotice from './VoteSourceReviewNotice'

const control = 'min-h-11 w-full rounded-md border border-slate-400 bg-white px-3 py-2 text-base text-slate-900 focus:outline-2 focus:outline-offset-2 focus:outline-civic-navy'
const linkClass = 'inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4 focus:outline-2 focus:outline-offset-2'
const defaults: CommonsSearchFilters = { q: '', mode: 'agenda', topic: '', from: '', to: '', page: 1 }
const money = (amount: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount)

function sourceLabel(source: string | null): string {
  return source === 'minutes' ? 'Extracted from official minutes' : source === 'transcript' ? 'Tentative — meeting recording' : 'Source not established'
}

export function AgendaRecord({ record }: { record: CommonsAgendaRecord }) {
  return <article className="rounded-xl border border-slate-300 bg-white p-5 sm:p-6">
    <p className="text-base text-slate-600">{formatCivicDate(record.meetingDate)} · Item {record.itemNumber}</p>
    <h2 className="mt-2 text-xl font-semibold leading-snug text-civic-navy"><Link className="inline-flex min-h-11 items-center underline decoration-slate-300 underline-offset-4" href={record.url}>{record.title}</Link></h2>
    {(record.topic || record.category) && <p className="mt-3 text-base text-slate-700">Tags: {[record.topic, record.category?.replaceAll('_', ' ')].filter(Boolean).join(' · ')}</p>}
    {record.voteSourceReview && <VoteSourceReviewNotice review={record.voteSourceReview} />}
    {record.kind === 'votes' && !record.voteSourceReview && <details className="mt-4 rounded-lg border border-slate-200 px-4">
      <summary className="min-h-11 cursor-pointer py-3 font-medium text-civic-navy">Recorded motions ({record.motions.length})</summary>
      <p className="mt-2 text-slate-600">These are automated extractions. Names, choices, and results may contain errors; check the original document before relying on them.</p>
      <ol className="divide-y divide-slate-200">{record.motions.map((motion, index) => <li key={motion.id} className="py-4">
        <h3 className="font-semibold text-slate-800">Motion {index + 1}</h3>
        {motion.text && <p className="mt-2 whitespace-pre-wrap leading-relaxed text-slate-700">{motion.text}</p>}
        <p className="mt-2 text-slate-700">{sourceLabel(motion.source)}{motion.result ? ` · Recorded result: ${motion.result}` : ' · Result not established'}</p>
        {motion.source === 'transcript' && <p className="mt-2 text-slate-600">Recording-derived votes remain tentative until the official minutes are available.</p>}
        {motion.votes.length ? <ul className="mt-3 space-y-1 text-slate-800">{motion.votes.map(vote => <li key={vote.id}>{vote.name || 'Name not established'}: <span className="font-medium">{vote.choice === 'not-recorded' ? 'Choice not established' : vote.choice}</span>{vote.source !== motion.source && <span className="text-slate-600"> · {sourceLabel(vote.source)}</span>}</li>)}</ul>
          : <p className="mt-3 text-slate-600">Individual vote choices are not indexed for this motion.</p>}
        <p className="mt-3 text-base text-slate-600">Indexed {formatCivicDate(motion.indexedAt)}.</p>
      </li>)}</ol>
      <div className="mb-3 flex flex-wrap gap-x-5">{record.minutesUrl && <a className={linkClass} href={record.minutesUrl} target="_blank" rel="noopener noreferrer">Official minutes</a>}{record.recordingUrl && <a className={linkClass} href={record.recordingUrl} target="_blank" rel="noopener noreferrer">Meeting recording</a>}</div>
    </details>}
    <footer className="mt-4 border-t border-slate-100 pt-3 text-base text-slate-600">
      <p>Official meeting record · Indexed {formatCivicDate(record.indexedAt)}.</p>
      <div className="flex flex-wrap gap-x-5"><a className={linkClass} href={record.sourceUrl} target="_blank" rel="noopener noreferrer">Original meeting document</a><Link className={linkClass} href={record.url}>Open the item and its records</Link></div>
    </footer>
  </article>
}

function MoneyRecord({ record }: { record: CommonsMoneyRecord }) {
  const row = record.event
  return <article className="rounded-xl border border-slate-300 bg-white p-5 sm:p-6">
    <p className="text-base text-slate-600">Activity reported {formatCivicDate(row.activity_date)}</p>
    <h2 className="mt-2 text-xl font-semibold text-civic-navy">{money(row.amount)} · {financeEventLabel(row)}</h2>
    {row.event_kind === 'independent_expenditure' ? <>
      <p className="mt-3 text-slate-800">Reported spender: {row.reporting_filer_name || 'Not established'}</p>
      <p className="mt-2 text-slate-800">{row.support_oppose === 'S' ? 'Supports' : row.support_oppose === 'O' ? 'Opposes' : 'Support or opposition not established'}: {row.candidate_name ?? row.measure_name ?? 'Target not established'}</p>
    </> : <><p className="mt-3 text-slate-800">From: {row.donor_name || 'Not established'}</p><p className="mt-2 text-slate-800">To: {row.recipient_name || 'Not established'}</p></>}
    {isFinanceAdjustment(row) && <p className="mt-3 text-slate-600">Signed adjustment to a reported value; this does not by itself establish a cash refund.</p>}
    {row.event_kind === 'loan' && <p className="mt-3 text-slate-600">This reported value may describe a loan balance or activity, rather than a new loan.</p>}
    <p className="mt-3 text-slate-600">{row.election_date ? `Election identified in the source: ${formatCivicDate(row.election_date)}.` : 'The source does not establish an election for this record.'}</p>
    <footer className="mt-4 border-t border-slate-100 pt-3 text-base text-slate-600">
      <p>Official campaign filing · Retrieved {formatCivicDate(row.extracted_at)}.</p>
      <p className="mt-1">Filing IDs: {row.filing_ids.join(', ') || 'Not established'}.</p>
      <div className="flex flex-wrap gap-x-5">{[...new Set(row.source_urls.length ? row.source_urls : [row.source_url])].map((url, index) => <a key={url} className={linkClass} href={url} target="_blank" rel="noopener noreferrer">Original filing {index + 1}</a>)}<Link className={linkClass} href={`/money?event=${encodeURIComponent(row.event_key)}#${encodeURIComponent(row.event_key)}`}>Open the money record</Link></div>
    </footer>
  </article>
}

export default function CommonsSearchClient() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()
  const urlState = searchParams.toString()
  const [draft, setDraft] = useState<CommonsSearchFilters>(defaults)
  const [response, setResponse] = useState<CommonsSearchResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const resultsRef = useRef<HTMLDivElement>(null)
  const requestId = useRef(0)

  useEffect(() => {
    const id = ++requestId.current
    const controller = new AbortController()
    const params = new URLSearchParams(urlState)
    let filters: CommonsSearchFilters
    try { filters = planCommonsSearch(params) } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Check the search filters.')
      setLoading(false)
      return () => controller.abort()
    }
    setDraft(filters)
    if (!urlState) { setLoading(false); setError(null); setResponse(null); return () => controller.abort() }
    setLoading(true)
    setError(null)
    async function load() {
      try {
        const result = await fetch(`/api/commons/search?${commonsSearchParams(filters)}`, { signal: controller.signal })
        const data = await result.json()
        if (!result.ok) throw new Error(typeof data.error === 'string' ? data.error : 'The source records could not be loaded.')
        if (id !== requestId.current) return
        setResponse(data as CommonsSearchResponse)
        resultsRef.current?.focus({ preventScroll: true })
      } catch (failure) {
        if (controller.signal.aborted || id !== requestId.current) return
        setError(failure instanceof Error ? failure.message : 'The source records could not be loaded. Please try again.')
      } finally { if (id === requestId.current) setLoading(false) }
    }
    void load()
    return () => controller.abort()
  }, [urlState, attempt])

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try {
      const plan = planCommonsSearch(commonsSearchParams({ ...draft, page: 1 }))
      const params = commonsSearchParams(plan).toString()
      if (pathname === '/search' && params === urlState) setAttempt(value => value + 1)
      else router.push(`/search?${params}`)
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Check the search filters.') }
  }
  function pageUrl(page: number) { return `/search?${commonsSearchParams({ ...(response?.filters ?? draft), page })}` }

  return <section aria-label="Search public records" className="space-y-5">
    <form action="/search" method="get" onSubmit={submit} className="rounded-xl border border-slate-300 bg-white p-5 sm:p-6">
      <label htmlFor="commons-query" className="block text-lg font-semibold text-civic-navy">Search decisions, votes, or campaign money</label>
      <div className="mt-3 flex flex-col gap-3 sm:flex-row"><input id="commons-query" name="q" type="search" maxLength={200} value={draft.q} onChange={event => setDraft({ ...draft, q: event.target.value })} placeholder="Housing decisions in 2026" className={control} /><button type="submit" className="min-h-11 rounded-md bg-civic-navy px-6 py-2 text-base font-semibold text-white focus:outline-2 focus:outline-offset-2 focus:outline-civic-navy">Search</button></div>
      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <div><label htmlFor="commons-mode" className="block font-medium text-slate-800">Look in</label><select id="commons-mode" name="mode" value={draft.mode} onChange={event => setDraft({ ...draft, mode: event.target.value as CommonsMode, topic: event.target.value === 'money' ? '' : draft.topic })} className={`${control} mt-2`}><option value="agenda">Agenda items</option><option value="votes">Votes</option><option value="money">Money</option></select></div>
        {draft.mode !== 'money' && <div><label htmlFor="commons-topic" className="block font-medium text-slate-800">Tag (exact match)</label><input id="commons-topic" name="topic" value={draft.topic} onChange={event => setDraft({ ...draft, topic: event.target.value })} list="commons-topics" maxLength={100} className={`${control} mt-2`} placeholder="Any tag" /><datalist id="commons-topics">{response?.topics.map(topic => <option value={topic} key={topic} />)}</datalist></div>}
        <div><label htmlFor="commons-from" className="block font-medium text-slate-800">{draft.mode === 'money' ? 'Activity from' : 'Meeting from'}</label><input id="commons-from" name="from" type="date" value={draft.from} onChange={event => setDraft({ ...draft, from: event.target.value })} className={`${control} mt-2`} /></div>
        <div><label htmlFor="commons-to" className="block font-medium text-slate-800">Through</label><input id="commons-to" name="to" type="date" value={draft.to} onChange={event => setDraft({ ...draft, to: event.target.value })} className={`${control} mt-2`} /></div>
      </div>
      <p className="mt-4 text-base leading-relaxed text-slate-600">Use names, topics, or simple phrases. This staged search recognizes a few question patterns and retrieves indexed records. Broader natural-language answers are still being prepared.</p>
    </form>
    {!response && !loading && !error && <div className="text-base text-slate-700"><p className="font-medium">Try a search</p><ul className="mt-1 flex flex-wrap gap-x-6"><li><Link className={linkClass} href="/search?q=Housing+decisions+in+2026&mode=agenda">Housing decisions in 2026</Link></li><li><Link className={linkClass} href="/search?q=Who+voted+on+Point+Molate%3F&mode=votes">Who voted on Point Molate?</Link></li><li><Link className={linkClass} href="/search?q=Donations+to+Jimenez&mode=money">Donations to Jimenez</Link></li></ul><p className="mt-2">Leave the search blank to browse. Tags suggested after a search come from the retrieved items.</p></div>}
    {loading && <div aria-live="polite" className="space-y-3"><p className="text-base text-slate-700">Loading source records…</p>{[0, 1].map(value => <div key={value} aria-hidden="true" className="rounded-xl border border-slate-200 bg-white p-6"><div className="h-4 w-36 rounded bg-slate-200" /><div className="mt-4 h-6 w-4/5 rounded bg-slate-200" /><div className="mt-5 h-4 w-3/5 rounded bg-slate-200" /></div>)}</div>}
    {error && <p role="alert" className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-base text-slate-800">{error} {response && 'Previously loaded records remain below.'}</p>}
    {response && <div ref={resultsRef} tabIndex={-1} className="space-y-5 focus:outline-none">
      <p role="status" className="text-base font-medium text-slate-800">{response.records.length} {response.records.length === 1 ? 'record' : 'records'} shown · page {response.filters.page}{response.total !== null ? ` · ${response.total} matches in ${response.limited ? 'the retrieved set' : 'this index'}` : ''}</p>
      <p className="text-base text-slate-700">Search interpreted as: {response.interpretation.join(' · ')}.</p>
      <aside className="rounded-lg bg-slate-100 p-4 text-base leading-relaxed text-slate-700">{response.limitations.map(limit => <p className="mt-2 first:mt-0" key={limit}>{limit}</p>)}</aside>
      {response.filters.mode === 'money' && <FinanceCoverageNote coverage={response.coverage} />}
      {response.records.length ? <div className="space-y-4">{response.records.map(record => record.kind === 'money' ? <MoneyRecord record={record} key={record.id} /> : <AgendaRecord record={record} key={record.id} />)}</div>
        : <p className="rounded-lg border border-slate-200 bg-white p-5 text-base text-slate-700">No indexed records matched this search. Try a shorter name or topic, or remove the tag and date filters. Missing matches do not establish that no decisions or payments occurred.</p>}
      <nav aria-label="Search result pages" className="flex justify-between gap-4">{response.filters.page > 1 ? <Link className={linkClass} href={pageUrl(response.filters.page - 1)}>← Previous page</Link> : <span />}{response.hasMore && <Link className={linkClass} href={pageUrl(response.filters.page + 1)}>Next page →</Link>}</nav>
    </div>}
  </section>
}
