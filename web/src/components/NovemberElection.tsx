import Link from 'next/link'
import SubscribeForm from '@/components/SubscribeForm'
import SuggestCorrectionLink from '@/components/SuggestCorrectionLink'
import PublishedCivicBriefs from '@/components/PublishedCivicBriefs'
import { getPublicFinanceSnapshot, candidateMoney, type FinanceEvent, type PublicFinanceSnapshot } from '@/lib/finance-public'
import { NOVEMBER_CANDIDATES, NOVEMBER_DATES, NOVEMBER_ELECTION as election, formatCivicDate } from '@/lib/november-election'

const money = (amount: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(amount)
const linkClass = 'inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4'

function OfficialSource({ href, children }: { href: string; children: React.ReactNode }) {
  return <p className="mt-3 text-sm text-slate-600"><span>Official record · checked September 6, 2026 · </span><a className={linkClass} href={href}>{children}</a></p>
}

function EventList({ events }: { events: FinanceEvent[] }) {
  return <ul className="divide-y divide-slate-200">
    {events.map(event => <li key={event.event_key} className="py-4">
      <p className="font-medium text-civic-navy">{money(event.amount)} · {event.event_kind === 'independent_expenditure' ? event.reporting_filer_name : event.donor_name ?? 'Contributor name unavailable'}</p>
      <p className="mt-1 text-slate-700">{event.event_kind === 'independent_expenditure'
        ? `Independent spending${event.support_oppose === 'S' ? ' supporting' : event.support_oppose === 'O' ? ' opposing' : ' mentioning'} ${event.candidate_name ?? event.measure_name ?? 'a ballot choice'}`
        : `Reported to ${event.recipient_name ?? 'a committee'}`}</p>
      <p className="mt-1 text-sm text-slate-600">Activity: {formatCivicDate(event.activity_date)} · {event.election_date ? `Election: ${formatCivicDate(event.election_date)}` : 'Election not identified in this record'}</p>
      <p className="text-sm text-slate-600">Official filing · retrieved {formatCivicDate(event.extracted_at)} · <a className={linkClass} href={event.source_url}>Read filing {event.filing_ids[0] ?? ''}</a></p>
    </li>)}
  </ul>
}

export default async function NovemberElection() {
  let snapshot: PublicFinanceSnapshot | null = null
  try { snapshot = await getPublicFinanceSnapshot() } catch (error) {
    console.error('[November finance]', error instanceof Error ? error.message : 'Unavailable')
  }
  const latest = snapshot?.events.filter(event => event.event_kind === 'independent_expenditure'
    || NOVEMBER_CANDIDATES.some(candidate => event.recipient_fppc_id === candidate.committeeId)).slice(0, 8) ?? []
  return <article className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
    <header className="max-w-3xl">
      <p className="text-sm font-semibold uppercase tracking-wide text-slate-600">Richmond, California · November 3, 2026</p>
      <h1 className="mt-3 text-3xl font-bold tracking-tight text-civic-navy sm:text-5xl">Your November decisions</h1>
      <p className="mt-5 text-lg leading-relaxed text-slate-700">Choose Richmond&apos;s next mayor and decide on a proposed $120 million fire-station bond. Follow the public record behind the choices: campaign money, council decisions, and what happens next.</p>
      <p className="mt-3 text-slate-600">This guide covers Richmond municipal decisions. Your ballot also includes other contests; use the <a href={election.county} className={linkClass}>county&apos;s official voter guide</a> for your full ballot.</p>
      <p className="mt-2 text-sm text-slate-500">AI-written explanation, checked against the official sources linked below.</p>
      <nav aria-label="On this page" className="mt-5 flex flex-wrap gap-x-6 gap-y-1">
        <a href="#choices" className={linkClass}>The choices</a><a href="#money" className={linkClass}>Follow the money</a><a href="#dates" className={linkClass}>Dates to save</a><a href="#en-espanol" className={linkClass} lang="es">En español</a>
      </nav>
    </header>

    <section id="choices" className="mt-12 scroll-mt-24 border-t border-slate-200 pt-8">
      <h2 className="text-2xl font-semibold text-civic-navy">The choices</h2>
      <div className="mt-5 grid gap-8 md:grid-cols-2">
        <article>
          <h3 className="text-xl font-semibold text-civic-navy">Mayor: Ahmad Anderson or Claudia Jimenez</h3>
          <p className="mt-3 leading-relaxed text-slate-700">The city certified these two candidates for the runoff after the June primary. The same resolution declared Cesar Zepeda, Doria Robinson, and Soheila Bana elected in council districts 2, 3, and 4; those are not additional November runoff races.</p>
          <OfficialSource href={election.certification}>City Resolution 119-26, July 21</OfficialSource>
        </article>
        <article>
          <h3 className="text-xl font-semibold text-civic-navy">A $120 million fire-station bond</h3>
          <p className="mt-3 leading-relaxed text-slate-700">The council placed borrowing for fire-station improvements on the ballot. The resolution requires two-thirds voter approval. Approval would authorize borrowing repaid through property taxes; it would not mean the construction was already delivered.</p>
          <p className="mt-3 leading-relaxed text-slate-700">The final county ballot designation is still being checked here. Use the official voter guide for the complete ballot wording.</p>
          <OfficialSource href={election.bondResolution}>City Resolution 143-26, July 28</OfficialSource>
          <Link href="/stories/fire-stations-and-emergency-response" className={linkClass}>Follow the fire-station story →</Link>
        </article>
      </div>
    </section>

    <PublishedCivicBriefs subjectKey="2026-general" />

    <section id="money" className="mt-12 scroll-mt-24 border-t border-slate-200 pt-8">
      <h2 className="text-2xl font-semibold text-civic-navy">Follow the money</h2>
      <p className="mt-3 max-w-3xl leading-relaxed text-slate-700">A donation goes to a campaign. Independent spending pays for activity supporting or opposing a candidate outside that campaign. Transfers between committees can fund later spending, so adding all three together would count some money twice.</p>
      <p className="mt-3 max-w-3xl text-slate-600">These are subtotals of the source reports indexed here, not complete fundraising totals. Cash gifts cover reported activity in 2026. The outside-spending columns require an explicitly identified November 3 election and support or opposition. Earlier or unidentified-election activity appears separately below.</p>
      {!snapshot ? <p role="status" className="mt-5 rounded-lg border border-amber-300 bg-amber-50 p-5 text-slate-800">Campaign records are temporarily unavailable here. This is a source-loading problem, not a finding of no donations or outside spending. The election guide and original sources remain available.</p> : <>
        {snapshot.truncated && <p role="status" className="mt-4 text-slate-700">This view reached its record limit; totals are withheld until the complete set can be read.</p>}
        <div className="mt-6 grid gap-5 md:grid-cols-2">
          {NOVEMBER_CANDIDATES.map(candidate => {
            const totals = candidateMoney(snapshot.events, candidate.committeeId, candidate.name)
            return <article key={candidate.committeeId} className="rounded-xl border border-slate-200 p-5">
              <h3 className="text-xl font-semibold text-civic-navy">{candidate.name}</h3>
              <p className="mt-1 text-sm text-slate-600">Candidate committee · FPPC {candidate.committeeId}</p>
              <dl className="mt-5 space-y-4">
                <div><dt className="text-slate-600">Indexed 2026 cash gifts</dt><dd className="mt-1 text-3xl font-semibold text-civic-navy">{totals.receipts.length && !snapshot.truncated ? money(totals.receiptsTotal) : 'Not established'}</dd></div>
                <div><dt className="text-slate-600">Independent November support</dt><dd className="font-semibold text-civic-navy">{totals.support.length && !snapshot.truncated ? money(totals.supportTotal) : 'No published matching records'}</dd></div>
                <div><dt className="text-slate-600">Independent November opposition</dt><dd className="font-semibold text-civic-navy">{totals.opposition.length && !snapshot.truncated ? money(totals.oppositionTotal) : 'No published matching records'}</dd></div>
              </dl>
              <p className="mt-4 text-sm leading-relaxed text-slate-600">Loans, noncash gifts, refunds, and outgoing transfers are separate from cash gifts. Missing records do not mean zero activity.</p>
              <Link className={linkClass} href={`/elections/2026-general/money?committee=${candidate.committeeId}`}>Read this committee&apos;s indexed records →</Link>
            </article>
          })}
        </div>
        <div className="mt-7">
          <h3 className="text-lg font-semibold text-civic-navy">What the source coverage includes</h3>
          {snapshot.coverage.length ? <ul className="mt-3 space-y-3">{snapshot.coverage.slice(0, 8).map(row => <li key={`${row.source}:${row.form_type}:${row.scope_key}`} className="text-sm leading-relaxed text-slate-600">
            <a href={row.source_url} className={linkClass}>{row.source} · {row.form_type}</a>: {row.status.replaceAll('_', ' ')} · checked {formatCivicDate(row.checked_at)}{row.activity_through ? ` · reported activity through ${formatCivicDate(row.activity_through)}` : ''}. {row.limitations.join(' ')}
          </li>)}</ul> : <p className="mt-3 text-slate-600">A complete source-coverage check has not yet been published. Treat the indexed records as a partial set.</p>}
        </div>
      </>}
      <div className="mt-8">
        <h3 className="text-lg font-semibold text-civic-navy">Recent indexed activity ({latest.length})</h3>
        {latest.length ? <EventList events={latest} /> : <p className="mt-3 text-slate-600">No reconciled entries are available in this view yet. That does not establish that no activity occurred.</p>}
        <Link href="/elections/2026-general/money" className={linkClass}>Open the source-linked money ledger →</Link>
      </div>
      <p className="mt-4 max-w-3xl leading-relaxed text-slate-700">Who is behind a committee? A filing can identify a union, company, or another committee as a contributor. That relationship is evidence about the reported transfer, not proof of influence over a vote. An independent committee is not automatically “dark money”; some disclose their donors, while other records stop at an organization whose original donors are not publicly identified.</p>
      <Link href="/elections/methodology" className={linkClass}>How these records are counted and checked</Link>
    </section>

    <section id="dates" className="mt-12 scroll-mt-24 border-t border-slate-200 pt-8">
      <h2 className="text-2xl font-semibold text-civic-navy">Dates to save</h2>
      <p className="mt-3 text-slate-700">Late contribution and independent-expenditure reporting runs August 5–November 3. A filing deadline is different from the last date of activity it covers.</p>
      <ol className="mt-5 divide-y divide-slate-200">{NOVEMBER_DATES.map(item => <li key={item.date} className="grid gap-1 py-4 sm:grid-cols-[10rem_1fr]">
        <time dateTime={item.date} className="font-semibold text-civic-navy">{formatCivicDate(item.date)}</time>
        <div><h3 className="font-semibold text-slate-800">{item.title}</h3><p className="mt-1 text-slate-600">{item.detail}</p></div>
      </li>)}</ol>
      <div className="flex flex-wrap gap-x-6"><a className={linkClass} href="/elections/2026-general/calendar.ics">Save these dates to your calendar</a><a className={linkClass} href="https://registertovote.ca.gov/">Register or update your registration</a></div>
      <OfficialSource href={election.votingDates}>California election dates</OfficialSource>
      <p className="text-sm text-slate-600">Official FPPC schedules: <a className={linkClass} href={election.filingSchedule}>candidate reports</a> · <a className={linkClass} href={election.independentSchedule}>independent spending reports</a></p>
    </section>

    <section id="en-espanol" lang="es" className="mt-12 scroll-mt-24 rounded-xl bg-slate-50 p-6">
      <h2 className="text-2xl font-semibold text-civic-navy">Lo esencial, en español</h2>
      <p className="mt-4 leading-relaxed text-slate-700">El 3 de noviembre, Richmond elegirá entre Ahmad Anderson y Claudia Jimenez para la alcaldía. También se propone autorizar $120 millones en bonos para mejorar las estaciones de bomberos. Esta guía cubre las decisiones municipales; consulte la guía oficial del condado para ver su boleta completa.</p>
      <p className="mt-3 leading-relaxed text-slate-700">La votación anticipada comienza el 5 de octubre. La fecha límite de inscripción ordinaria es el 19 de octubre; la inscripción condicional sigue disponible del 20 de octubre al 3 de noviembre. El día de las elecciones, las urnas abren de 7 a. m. a 8 p. m.</p>
      <p className="mt-3 text-sm text-slate-600">Explicación redactada con IA y cotejada con las fuentes oficiales anteriores el 6 de septiembre de 2026.</p>
      <a className={linkClass} href={election.county}>Información electoral oficial del condado →</a>
    </section>

    <section className="mt-12 max-w-xl border-t border-slate-200 pt-8">
      <h2 className="text-2xl font-semibold text-civic-navy">Keep up with Richmond</h2>
      <p className="my-4 leading-relaxed text-slate-700">Subscribe to the existing council briefing for meeting context and public records. Election-specific alerts will be listed here when available.</p>
      <SubscribeForm surface="november_election" />
    </section>
    <footer className="mt-10 text-sm text-slate-600"><SuggestCorrectionLink /><p className="mt-3">Richmond Commons. “Your November decisions.” richmondcommons.org/elections/2026-general. Official guide facts checked September 6, 2026; finance retrieval dates shown with each filing.</p></footer>
  </article>
}
