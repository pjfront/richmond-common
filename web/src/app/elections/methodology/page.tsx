import type { Metadata } from 'next'
import Link from 'next/link'

export const metadata: Metadata = {
  title: 'How we show campaign money',
  description: 'How Richmond Commons distinguishes campaign-reported totals, individual filing entries, and outside spending.',
}

export default function ElectionsMethodologyPage() {
  return <article className="mx-auto max-w-3xl px-4 py-8 sm:px-6 lg:px-8">
    <Link href="/elections" className="inline-flex min-h-11 items-center text-civic-navy underline">← Elections</Link>
    <h1 className="mt-4 text-3xl font-bold text-civic-navy">How we show campaign money</h1>
    <p className="mt-3 leading-relaxed text-slate-700">A campaign total and an individual filing entry answer different questions. We keep each amount with the committee, dates and source that explain it.</p>
    <p className="mt-2 text-sm text-slate-600">Methodology updated September 10, 2026.</p>

    <section className="mt-8" id="campaign-summaries">
      <h2 className="text-xl font-semibold text-civic-navy">What a campaign reports raising</h2>
      <p className="mt-3 leading-relaxed text-slate-700">A dated campaign summary uses the amounts declared in the original reports. We check the reporting periods and amendments before combining periods. An overlapping report is not added twice. Cash donations, loans and noncash support remain separate.</p>
      <p className="mt-3 leading-relaxed text-slate-700">A later report of an individual donation does not establish a complete fundraising total since the last periodic report. Its receipt date can also be earlier than its filing date. The summary states both what period is covered and what remains unconfirmed.</p>
      <p className="mt-3 leading-relaxed text-slate-700">The original reports and the date of our source check appear alongside each summary. A newer filing triggers a coverage notice; it does not silently replace a checked total. Checking summary arithmetic does not mean every donor entry has been reconciled.</p>
      <Link href="/elections/2026-general#money" className="mt-2 inline-flex min-h-11 items-center text-civic-navy underline">Read the dated mayoral campaign summaries →</Link>
    </section>

    <section id="reconciled-ledger" className="mt-8 scroll-mt-24">
      <h2 className="text-xl font-semibold text-civic-navy">Individual 2026 money records</h2>
      <ul className="mt-3 list-disc space-y-3 pl-5 leading-relaxed text-slate-700">
        <li>Multiple filings can describe the same contribution. The index keeps the original statements, follows explicit amendment links and connects matching reports. Equal amounts and nearby dates alone do not prove that two entries are duplicates.</li>
        <li>Cash contributions, loans, noncash support, refunds, outgoing contributions and independent expenditures are different kinds of activity. A committee transfer and the recipient committee’s later spending are not added as if they were two amounts of new money.</li>
        <li>A receipt report matching a loan or noncash entry cannot establish an additional cash gift. Conflicting cash claims wait for source review. A loan schedule may describe a balance or activity; its amount is not automatically new borrowing.</li>
        <li>Separate spending reports can repeat an expense even when neither directly replaces the other. Exact repeated descriptions, parties, dates and amounts prompt review; both entries wait outside the public list until the sources settle whether they represent one expense or separate purchases. The original statements are retained.</li>
        <li>The cash-contribution filter includes both contributions received and contributions made. A committee’s role determines which direction is shown, regardless of which side filed the report. The download uses the same filters.</li>
        <li>The dates searched and the forms available are shown with the records. A partial index is not a campaign’s complete fundraising. If a read is incomplete or fails, we withhold the affected totals or export.</li>
        <li>Outside spending is separate from the candidate’s campaign. Support or opposition must come from the filing. A candidate’s name without an identified election does not establish spending for the November election.</li>
        <li>Committee links use reported FPPC identifiers. Similar names, shared addresses and treasurers do not establish ownership or control. An employee’s donation is not the employer’s donation. A nonprofit’s disclosed payment does not reveal its undisclosed funders.</li>
        <li>A sponsor explanation comes from a checked organization report, with its date and exact pages. Sponsorship and giving money are separate relationships. The existing source monitor queues new or changed reports for review; it cannot automatically change the public explanation.</li>
        <li>The extraction threshold is a publication check, not a statistical probability that a political claim is true. Passing that check does not prove influence, wrongdoing or a causal link to a vote.</li>
      </ul>
      <Link href="/elections/2026-general/money" className="mt-2 inline-flex min-h-11 items-center text-civic-navy underline">Search the 2026 records and original sources →</Link>
    </section>

    <section id="historical-records" className="mt-8 scroll-mt-24">
      <h2 className="text-xl font-semibold text-civic-navy">Older campaign records</h2>
      <p className="mt-3 leading-relaxed text-slate-700">Council and donor profiles also contain older imported entries. These can include overlapping reports, amendments, transfers, loans and noncash support. We display the individual entries and their reported kinds, without treating their sum as fundraising or counting names as unique people.</p>
      <p className="mt-3 leading-relaxed text-slate-700">Year filters mean the calendar year of the reported activity. They do not assign the money to an election. A committee’s name identifies the reported recipient; a transfer from an older campaign can be existing campaign money.</p>
      <p className="mt-3 leading-relaxed text-slate-700">The historical donor directory retains its existing limited selection of profiles, selected using the legacy index’s $5,000 inclusion threshold. That cached threshold is not presented as a verified lifetime total. Names and employers are as reported; variants may describe the same person, and an old employer field may no longer be current.</p>
    </section>

    <section id="campaign-record-csv-field-guide" className="mt-8 scroll-mt-24">
      <h2 className="text-xl font-semibold text-civic-navy">Reading the downloads</h2>
      <p className="mt-3 leading-relaxed text-slate-700">Each CSV contains the entries in that view. Amounts belong to the named activity, date and committee. Original filing links let you inspect the source. A blank value means it has not been established; it does not mean zero.</p>
      <dl className="mt-4 space-y-4 text-sm leading-relaxed text-slate-700">
        <div><dt className="font-semibold">Names and committee IDs</dt><dd>Reported names identify the parties. FPPC IDs are registration numbers; recipient_committee_id is an internal record ID, not a committee registration number. An employer field does not identify the donor of a personal gift.</dd></div>
        <div><dt className="font-semibold">Amounts, dates and activity kinds</dt><dd>Read amount with contribution_type or event_kind. Contribution and expenditure dates describe reported activity; filing dates describe when the report was submitted. Neither alone identifies an election. On independent-spending exports, support_or_oppose uses the filing’s code: S means support, O means oppose; a blank value means no direction is established.</dd></div>
        <div><dt className="font-semibold">Sources and review status</dt><dd>filing_id and source_url point to the source report when available. Reconciliation status describes how multiple reported entries were handled. Historical imports do not carry a guarantee that every repeated report has been reconciled.</dd></div>
      </dl>
    </section>
  </article>
}
