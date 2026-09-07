import type { Metadata } from 'next'
import Link from 'next/link'
import { BUCKETS, SOURCE_TYPES } from '@/lib/contributionBuckets'

export const metadata: Metadata = {
  title: 'How We Show Campaign Contributions | Richmond Commons',
  description:
    'A plain-language guide to the dollar amounts and donor categories used on Richmond candidate pages, with citations to the California rules behind each one.',
}

// Public methodology page — the regulatory rules cited here are
// independently verifiable from primary sources (FPPC manuals, Cal. Gov.
// Code, Richmond Municipal Code). The candidate-page bucket display that
// links here is currently operator-gated; the methodology itself doesn't
// need to be, so it's published openly for anyone reviewing the design.

export default function ElectionsMethodologyPage() {
  return (
    <article className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <nav className="mb-6">
        <Link
          href="/elections"
          className="text-sm text-civic-navy-light hover:text-civic-navy"
        >
          ← Elections
        </Link>
      </nav>

      <header className="mb-8">
        <h1 className="text-3xl font-bold text-civic-navy tracking-tight">
          How we show campaign contributions
        </h1>
        <p className="text-slate-600 mt-2 leading-relaxed">
          On each candidate&apos;s page we group contributions into a small
          grid by donor type and dollar amount. The grid isn&apos;t a design
          choice — every line in it is tied to a real California campaign
          finance rule. This page explains what each line means and where it
          comes from.
        </p>
      </header>

      <section id="reconciled-ledger" className="mb-12 scroll-mt-24">
        <h2 className="text-xl font-bold text-civic-navy">The 2026 source-linked ledger</h2>
        <p className="mt-3 leading-relaxed text-slate-700">The November guide and its money ledger use a separate, reconciled set of source reports. The older donor categories described later on this page are not used to infer ownership or control in that ledger.</p>
        <ul className="mt-4 list-disc space-y-3 pl-5 leading-relaxed text-slate-700">
          <li>A filing is a statement made by its filer. Multiple filings can describe one contribution. The index retains the original source assertions and links matching reports; it does not erase two gifts merely because their amounts are equal and their dates are close.</li>
          <li>Cash gifts, loans, noncash contributions, refunds, outgoing contributions, and independent expenditures are different kinds of activity. Candidate cash-gift subtotals exclude the other kinds. Upstream committee transfers are not added to downstream advertising as a single spending total.</li>
          <li>Amendments follow the source system&apos;s explicit filing lineage. An ambiguous match remains outside the reconciled public totals pending review. Source coverage and gaps appear on the guide; a partial set is not a candidate&apos;s complete fundraising total.</li>
          <li>Independent support or opposition comes from the filing. A source that identifies a candidate but not an election cannot contribute to a November-specific spending total. Earlier and unidentified-election records remain visible with their activity dates.</li>
          <li>Committee links use reported FPPC identifiers. A person&apos;s employer is not treated as the donor of that person&apos;s gift. Similar names, addresses, or treasurers do not establish ownership, control, or the original source of a nonprofit&apos;s funding.</li>
          <li>The public projection preserves the existing 90% extraction threshold and requires source attribution. That threshold is an extraction rule, not a statistical probability that a political claim is true.</li>
          <li>Downloads contain reported names, committee identifiers, dates, amounts, event types, reconciliation status, and original filing URLs. They omit street addresses and private review material. Blank cells mean a value has not been established.</li>
        </ul>
        <p className="mt-4 text-sm text-slate-600">Methodology version: September 6, 2026. Read the <Link href="/elections/2026-general/money" className="inline-flex min-h-11 items-center text-civic-navy underline">2026 money ledger</Link> and follow each original source. Reporting deadlines are linked in the November guide.</p>
      </section>

      {/* ── Amount buckets ─────────────────────────────────────── */}
      <section className="mb-12">
        <h2 className="text-xl font-bold text-civic-navy mb-2">
          Dollar amount groups
        </h2>
        <p className="text-sm text-slate-600 mb-6 leading-relaxed">
          Each row in the grid is a dollar range with a real meaning. Crossing
          one of these boundaries triggers a new disclosure rule, a new ethics
          rule, or hits the legal cap for a single contribution.
        </p>

        <div className="space-y-5">
          {BUCKETS.map((b) => (
            <div
              key={b.key}
              className="border border-slate-200 rounded-lg p-5"
            >
              <h3 className="text-base font-semibold text-civic-navy">
                {b.plainLabel}
              </h3>
              <p className="text-sm text-slate-700 mt-2 leading-relaxed">
                {b.rationale}
              </p>
              <p className="text-xs text-slate-400 mt-2">
                Source: {b.source}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Source types ───────────────────────────────────────── */}
      <section className="mb-12">
        <h2 className="text-xl font-bold text-civic-navy mb-2">
          Who&apos;s giving
        </h2>
        <p className="text-sm text-slate-600 mb-6 leading-relaxed">
          Each column in the grid is a type of giver. The label comes from
          how the contribution was reported on the candidate&apos;s filing.
        </p>

        <div className="space-y-5">
          {SOURCE_TYPES.map((s) => (
            <div
              key={s.key}
              className="border border-slate-200 rounded-lg p-5"
            >
              <h3 className="text-base font-semibold text-civic-navy">
                {s.label}
              </h3>
              <p className="text-sm text-slate-700 mt-2 leading-relaxed">
                {s.description}
              </p>
            </div>
          ))}
        </div>

        <p className="text-xs text-slate-500 mt-6 leading-relaxed">
          How we decide the type: we use the filing&apos;s own donor code when
          one is provided (the state assigns codes like &ldquo;IND&rdquo; for
          individual and &ldquo;COM&rdquo; for committee). When no code is
          provided we read the donor&apos;s name for the standard markers —
          words like &ldquo;Union,&rdquo; &ldquo;LLC,&rdquo; or
          &ldquo;PAC.&rdquo; The classification logic is in{' '}
          <code className="text-[11px] bg-slate-100 px-1 py-0.5 rounded">
            src/contributor_classifier.py
          </code>{' '}
          in the project repo.
        </p>
      </section>

      <section
        id="campaign-record-csv-field-guide"
        className="mb-12 scroll-mt-6"
      >
        <h2 className="text-xl font-bold text-civic-navy mb-2">
          Campaign record CSV field guide
        </h2>
        <p className="text-sm text-slate-600 mb-6 leading-relaxed">
          Downloads from council, political committee, union, and company profiles use
          one row per tracked filing record. Blank cells mean the source record
          did not provide a value; Richmond Commons does not fill them in.
        </p>
        <dl className="divide-y divide-slate-200 rounded-lg border border-slate-200">
          <CsvField
            name="donor_name, donor_employer"
            meaning="The contributor name and employer written on the filing. Employer may be blank."
          />
          <CsvField
            name="recipient_committee_name, recipient_candidate_name"
            meaning="The receiving committee and, when known, the candidate associated with it."
          />
          <CsvField
            name="recipient_committee_id"
            meaning="The Richmond Commons identifier for a matched receiving committee. It is not a committee registration number and may be blank."
          />
          <CsvField
            name="committee_name, committee_fppc_id"
            meaning="The receiving campaign committee and its state registration number for council-profile donation records. These identify the committee, not the election."
          />
          <CsvField
            name="source, source_url"
            meaning="The source service and original report link retained with the donation record. A missing link stays blank."
          />
          <CsvField
            name="candidate_name"
            meaning="The candidate or beneficiary named on an independent-expenditure record. It may be blank."
          />
          <CsvField
            name="support_or_oppose"
            meaning="The filing's direction code: S means support, O means oppose, and blank means the direction was not reported."
          />
          <CsvField
            name="amount"
            meaning="The dollar amount on that individual filing record, not an aggregate calculated by Richmond Commons."
          />
          <CsvField
            name="contribution_date, expenditure_date"
            meaning="The date reported for the contribution or expenditure, written as YYYY-MM-DD."
          />
          <CsvField
            name="contribution_type, expenditure_code"
            meaning="Codes carried from the filing for the kind of contribution or expenditure. Unknown or missing codes stay blank."
          />
          <CsvField
            name="payee_name, description"
            meaning="The payee and description reported for an independent expenditure. Either may be blank."
          />
          <CsvField
            name="filing_id"
            meaning="The filing identifier supplied with the source record. It may be blank when the imported record did not include one."
          />
        </dl>
      </section>

      {/* ── Why this matters ──────────────────────────────────── */}
      <section className="mb-12">
        <h2 className="text-xl font-bold text-civic-navy mb-2">
          What the grid is good for
        </h2>
        <div className="space-y-4 text-sm text-slate-700 leading-relaxed">
          <p>
            Two candidates can raise the same dollar amount in very
            different ways. One might raise $40,000 from sixteen people who
            each gave the $2,500 cap. Another might raise $40,000 from four
            hundred people who each gave $100. The total is the same; the
            picture isn&apos;t.
          </p>
          <p>
            The grid lets you see that picture in one glance. A heavy
            column under &ldquo;Union&rdquo; or &ldquo;PAC&rdquo; means
            organized money. A heavy row at &ldquo;Under $100&rdquo; means a
            broad small-donor base. A heavy bottom-right corner means
            cap-hitting donors who care a lot about this race.
          </p>
        </div>
      </section>

      {/* ── Data source ───────────────────────────────────────── */}
      <section className="mb-12">
        <h2 className="text-xl font-bold text-civic-navy mb-2">
          Where the numbers come from
        </h2>
        <p className="text-sm text-slate-700 leading-relaxed">
          Every contribution comes from the City of Richmond&apos;s public
          e-filing system,{' '}
          <a
            href="https://public.netfile.com/pub2/?AID=RICH"
            target="_blank"
            rel="noopener noreferrer"
            className="text-civic-navy hover:underline"
          >
            NetFile
          </a>
          . Each candidate&apos;s committee files reports on a schedule set
          by California law (Form 460 every six months, plus Form 497 within
          24 hours of any single contribution of $1,000 or more in the 90
          days before an election). We pull from those reports directly. No
          modeling, no estimates.
        </p>
        <p className="text-sm text-slate-500 mt-4 leading-relaxed">
          We follow the candidate&apos;s own report for the headline total
          (the &ldquo;raised $X&rdquo; line). The grid underneath re-groups
          contributions by amount and donor type so you can see the shape.
        </p>
        <p className="text-sm text-slate-500 mt-3 leading-relaxed">
          We only show the grid when the contributions we have on file add
          up to the candidate&apos;s headline total. When they don&apos;t
          &mdash; usually because of a Form 497 late-filing that hasn&apos;t
          been rolled into the next Form 460 yet, or a paper filing still
          being processed &mdash; we show the headline alone. The honest
          choice is to wait until the breakdown matches rather than show a
          grid that disagrees with the headline.
        </p>
      </section>

      {/* ── Caveats ───────────────────────────────────────────── */}
      <section className="mb-12">
        <h2 className="text-xl font-bold text-civic-navy mb-2">
          Honest caveats
        </h2>
        <ul className="space-y-3 text-sm text-slate-700 leading-relaxed list-disc list-inside">
          <li>
            <strong>Late-filed contributions can shift the picture.</strong>{' '}
            We refresh from NetFile hourly. Anything filed in the last hour
            may not be reflected yet.
          </li>
          <li>
            <strong>Amendments can change past numbers.</strong> Candidates
            sometimes amend earlier filings (correcting a typo, refunding a
            contribution). When that happens, our numbers update — they
            don&apos;t stay frozen at the original reading.
          </li>
          <li>
            <strong>Donor names aren&apos;t deduplicated by person.</strong>{' '}
            If &ldquo;Jane Smith&rdquo; gives $100 and &ldquo;Jane S.
            Smith&rdquo; gives $100, those count as two donors in the totals
            on the candidate page, even though they&apos;re probably the
            same person.
          </li>
          <li>
            <strong>
              The &ldquo;Business&rdquo; column counts donor businesses, not
              the businesses where individual donors work.
            </strong>{' '}
            If five Chevron employees each donate as individuals, those are
            counted as individual contributions, not business contributions.
            Chevron Corp. itself would have to be the donor for it to land in
            the Business column.
          </li>
        </ul>
      </section>

      <footer className="mt-12 pt-6 border-t border-slate-100 text-xs text-slate-400 leading-relaxed">
        <p>
          Methodology last updated when the rules change. Source citations on
          this page point to the primary regulatory text — please report any
          drift if you spot it.
        </p>
      </footer>
    </article>
  )
}

function CsvField({ name, meaning }: { name: string; meaning: string }) {
  return (
    <div className="grid gap-1 p-4 sm:grid-cols-[minmax(12rem,1fr)_2fr] sm:gap-4">
      <dt>
        <code className="break-words text-xs font-semibold text-civic-navy">
          {name}
        </code>
      </dt>
      <dd className="text-sm leading-relaxed text-slate-700">{meaning}</dd>
    </div>
  )
}
