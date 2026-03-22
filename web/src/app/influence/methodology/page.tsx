import type { Metadata } from 'next'
import Link from 'next/link'
import OperatorGate from '@/components/OperatorGate'

export const metadata: Metadata = {
  title: 'Methodology — Campaign Finance Data',
  description: 'How Richmond Common collects, matches, and presents campaign finance data alongside council voting records.',
}

export default function MethodologyPage() {
  return (
    <OperatorGate>
      <MethodologyContent />
    </OperatorGate>
  )
}

function MethodologyContent() {
  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <nav className="mb-6">
        <Link href="/meetings" className="text-sm text-civic-navy-light hover:text-civic-navy">
          ← Meetings
        </Link>
      </nav>

      <h1 className="text-2xl font-bold text-civic-navy mb-6">
        How We Present Campaign Finance Data
      </h1>

      {/* Data Sources */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold text-civic-navy mb-3">Data Sources</h2>
        <div className="space-y-4">
          <div className="bg-white border border-slate-200 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-slate-800">NetFile (City of Richmond)</h3>
            <p className="text-xs text-slate-600 mt-1 leading-relaxed">
              Local campaign finance filings for Richmond city council candidates.
              Richmond adopted NetFile for electronic filing in January 2018.
              This is the primary source for local campaign contributions.
            </p>
            <p className="text-xs text-slate-500 mt-1">Tier 1 · Official government records</p>
          </div>

          <div className="bg-white border border-slate-200 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-slate-800">CAL-ACCESS (California Secretary of State)</h3>
            <p className="text-xs text-slate-600 mt-1 leading-relaxed">
              Statewide campaign finance database. Contains PAC contributions,
              independent expenditure committees, and ballot measure spending.
              Individual council candidates file locally through NetFile, not CAL-ACCESS.
            </p>
            <p className="text-xs text-slate-500 mt-1">Tier 1 · Official government records</p>
          </div>

          <div className="bg-white border border-slate-200 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-slate-800">FPPC Form 700 (Statement of Economic Interests)</h3>
            <p className="text-xs text-slate-600 mt-1 leading-relaxed">
              Annual financial disclosure filings required of public officials.
              Reports real property, investments, income, gifts, and business positions.
            </p>
            <p className="text-xs text-slate-500 mt-1">Tier 1 · Official government records</p>
          </div>

          <div className="bg-white border border-slate-200 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-slate-800">FPPC Form 803 (Behested Payments)</h3>
            <p className="text-xs text-slate-600 mt-1 leading-relaxed">
              When an elected official asks a company or person to donate money
              to a specific cause or organization, California law requires them
              to report it. These are called &quot;behested payments.&quot; The money goes to
              the organization, not to the official. Officials file Form 803 with
              the FPPC to disclose these requests.
            </p>
            <p className="text-xs text-slate-500 mt-1">Tier 1 · Official government records</p>
          </div>
        </div>
      </section>

      {/* Entity Matching */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold text-civic-navy mb-3">Entity Matching</h2>
        <p className="text-sm text-slate-700 leading-relaxed mb-3">
          Campaign finance records are matched to agenda items using entity resolution —
          comparing names of donors, vendors, and organizations mentioned in agenda text
          against campaign contribution records. The matching algorithm uses:
        </p>
        <ul className="list-disc list-inside text-sm text-slate-700 space-y-1.5 ml-2">
          <li>Exact name matching with normalization (case, punctuation, common abbreviations)</li>
          <li>Substring matching for organization names that appear within longer agenda text</li>
          <li>CAL-ACCESS filer ID matching for committee cross-references</li>
          <li>Temporal weighting — more recent contributions receive higher confidence</li>
          <li>Financial materiality — larger contributions relative to total fundraising</li>
        </ul>
      </section>

      {/* Confidence Scores */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold text-civic-navy mb-3">Confidence Scores</h2>
        <p className="text-sm text-slate-700 leading-relaxed mb-3">
          Every match between a campaign finance record and an agenda item carries
          a confidence score reflecting how certain we are that the match is correct.
        </p>
        <div className="space-y-2">
          <div className="flex items-center gap-3">
            <span className="inline-block text-xs font-semibold px-2 py-0.5 rounded bg-red-100 text-red-800 border border-red-200">
              Strong
            </span>
            <span className="text-sm text-slate-600">85%+ — High-confidence match based on multiple signals</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="inline-block text-xs font-semibold px-2 py-0.5 rounded bg-yellow-100 text-yellow-800 border border-yellow-200">
              Moderate
            </span>
            <span className="text-sm text-slate-600">70–84% — Clear pattern with supporting evidence</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="inline-block text-xs font-semibold px-2 py-0.5 rounded bg-green-100 text-green-800 border border-green-200">
              Low
            </span>
            <span className="text-sm text-slate-600">50–69% — Possible match with limited evidence</span>
          </div>
        </div>
        <p className="text-sm text-slate-500 mt-3 italic">
          Confidence scores measure match accuracy, not the likelihood that a
          contribution influenced a decision. A 95% confidence score means we are
          very sure the record matches the right person — not that there is a 95%
          chance of wrongdoing.
        </p>
      </section>

      {/* Known Data Gaps */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold text-civic-navy mb-3">Known Data Gaps</h2>
        <div className="space-y-3">
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
            <p className="text-sm font-medium text-slate-700">Local Form 803 filings</p>
            <p className="text-xs text-slate-600 mt-1">
              FPPC bulk data covers state-level officials only. Local officials may
              file separately through a system not yet integrated.
            </p>
          </div>
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
            <p className="text-sm font-medium text-slate-700">Lobbyist registry</p>
            <p className="text-xs text-slate-600 mt-1">
              Richmond requires lobbyist registration under Municipal Code Chapter 2.54,
              but filings are paper/PDF only. No machine-readable format or searchable
              database exists. Richmond Common cannot programmatically verify registration status.
            </p>
          </div>
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
            <p className="text-sm font-medium text-slate-700">Charitable giving disclosure</p>
            <p className="text-xs text-slate-600 mt-1">
              Companies without an associated nonprofit overseeing their giving are not
              required to disclose charitable donations. Significant community investment
              may exist without public disclosure.
            </p>
          </div>
        </div>
      </section>

      {/* Why We Show This */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold text-civic-navy mb-3">Why We Show This Data</h2>
        <p className="text-sm text-slate-700 leading-relaxed mb-3">
          Campaign contributions are part of the public record. California law requires
          their disclosure specifically so citizens can understand the financial
          relationships between contributors and elected officials.
        </p>
        <p className="text-sm text-slate-700 leading-relaxed mb-3">
          Richmond Common presents this data because it is already public and citizens
          deserve to access it alongside the decisions it may relate to. We do not
          make judgments about whether any contribution influenced any decision —
          we present the factual record with context.
        </p>
        <p className="text-sm text-slate-700 leading-relaxed">
          If you believe any record is incorrect, please use the{' '}
          <Link href="#" className="text-civic-navy hover:underline">feedback system</Link> to
          report it.
        </p>
      </section>

      {/* Behested Payments Explanation */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold text-civic-navy mb-3">Behested Payments</h2>
        <p className="text-sm text-slate-700 leading-relaxed mb-3">
          Behested payments reveal a different kind of relationship than campaign
          contributions. They show which organizations and causes officials actively
          direct resources toward, and which companies and individuals respond to those
          requests. This is public information that helps citizens understand the full
          picture of how money flows around government decisions.
        </p>
        <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
          <p className="text-xs text-slate-600">
            <strong>Source:</strong> FPPC bulk data download (Tier 1, official government filings)
          </p>
          <p className="text-xs text-slate-600 mt-1">
            <strong>Coverage:</strong> State-level officials (Assembly, Senate, Governor).
            Local officials may file through separate systems not yet captured.
          </p>
          <p className="text-xs text-slate-600 mt-1">
            <strong>Threshold:</strong> Only payments of $5,000+ per year are required to be disclosed.
          </p>
          <p className="text-xs text-slate-600 mt-1">
            <strong>Note:</strong> Absence of a filing does not confirm absence of behesting.
            Officials may request payments below the disclosure threshold.
          </p>
        </div>
      </section>

      {/* Footer */}
      <div className="border-t border-slate-200 pt-6 text-xs text-slate-400">
        <p>
          All source data is public under California Government Code §81008.
          Richmond Common is a governance transparency tool, not an adversarial watchdog.
        </p>
      </div>
    </div>
  )
}
