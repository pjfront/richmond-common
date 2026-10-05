import { getBasicSourceRefreshStatus } from '@/lib/queries/basic-source-status'
import { basicSourceScope, formatSourceCheckTimestamp, type BasicSourceCheck, type BasicSourceStatus } from '@/lib/basic-source-status'

function CheckTime({ check }: { check: BasicSourceCheck }) {
  if (check.state === 'unavailable') return <p>Source check time is unavailable. Saved records may still be searchable.</p>
  if (!check.checkedAt) return <p>No source check has been recorded yet. Saved records may still be searchable.</p>
  return <p>Source last checked <time dateTime={check.checkedAt}>{formatSourceCheckTimestamp(check.checkedAt)}</time>.</p>
}

export function BasicSourceRefreshStatusView({ status }: { status: BasicSourceStatus }) {
  return (
    <section aria-labelledby="source-checks-heading" className="mt-6 rounded-lg border border-slate-200 bg-slate-50 p-4 text-base leading-relaxed text-slate-700 sm:p-5">
      <h2 id="source-checks-heading" className="font-semibold text-civic-navy">Source checks</h2>
      <div className="mt-3 grid gap-4 sm:grid-cols-2">
        <div>
          <h3 className="font-semibold text-civic-navy">Agendas</h3>
          <CheckTime check={status.agenda_refresh} />
          <p className="mt-1">{basicSourceScope(status.agenda_refresh)} New votes await review.</p>
          <a href="https://pub-richmond.escribemeetings.com/" className="inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4">Official meeting portal · Tier 1</a>
        </div>
        <div>
          <h3 className="font-semibold text-civic-navy">Campaign money</h3>
          <CheckTime check={status.finance} />
          <p className="mt-1">{basicSourceScope(status.finance)} {status.finance.state === 'pending_review' ? 'The saved 2026 index is awaiting review before a new reporting window is added. ' : ''}Paper filings await review; these records do not establish complete campaign totals.</p>
          <a href="https://public.netfile.com/pub2/?AID=RICH" className="inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4">Official electronic filings · Tier 1</a>
        </div>
      </div>
    </section>
  )
}

export function SourceRefreshLoading() {
  return <div className="mt-6 rounded-lg border border-slate-200 p-4" aria-live="polite" aria-busy="true"><p className="text-base text-slate-700">Loading source check times…</p><div aria-hidden="true" className="mt-3 h-16 rounded bg-slate-100" /></div>
}

export default async function BasicSourceRefreshStatus() {
  const status = await getBasicSourceRefreshStatus()
  return status ? <BasicSourceRefreshStatusView status={status} /> : null
}
