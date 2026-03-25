'use client'

import OperatorGate from '@/components/OperatorGate'

export function OperatorMethodology() {
  return (
    <OperatorGate>
      {/* Source Credibility Tiers — operator-only methodology */}
      <section className="mb-10">
        <h2 className="text-xl font-semibold text-civic-navy mb-3">Source Credibility Tiers</h2>
        <div className="space-y-3 text-slate-700 leading-relaxed">
          <p>
            All data is tagged with a credibility tier. Higher tiers carry more weight in analysis.
          </p>
          <div className="space-y-3">
            <TierCard
              tier={1}
              label="Official Records"
              color="bg-green-50 border-green-200"
              description="Certified minutes, adopted resolutions, CAL-ACCESS filings, budget documents. Highest reliability."
            />
            <TierCard
              tier={2}
              label="Independent Journalism"
              color="bg-blue-50 border-blue-200"
              description="Richmond Confidential (UC Berkeley), East Bay Times, KQED. Editorially independent reporting."
            />
            <TierCard
              tier={3}
              label="Stakeholder Communications"
              color="bg-amber-50 border-amber-200"
              description="Council member newsletters, Tom Butt E-Forum, Richmond Standard (Chevron-funded). Bias is always disclosed."
            />
            <TierCard
              tier={4}
              label="Community / Social"
              color="bg-slate-50 border-slate-200"
              description="Nextdoor, public comments, social media. Used for context only, never as a sole source for factual claims."
            />
          </div>
        </div>
      </section>

      {/* Conflict Scanner Methodology — operator-only */}
      <section className="mb-10">
        <h2 className="text-xl font-semibold text-civic-navy mb-3">How the Conflict Scanner Works</h2>
        <div className="space-y-3 text-slate-700 leading-relaxed">
          <ol className="list-decimal list-inside space-y-3 text-slate-700">
            <li>
              <strong>Document ingestion:</strong> We download agendas, minutes, and staff reports
              from Richmond&apos;s eSCRIBE portal and Archive Center.
            </li>
            <li>
              <strong>AI extraction:</strong> Claude Sonnet extracts structured data from documents:
              agenda items, motions, votes, financial amounts, departments.
            </li>
            <li>
              <strong>Cross-referencing:</strong> Each agenda item is compared against 27,000+
              campaign contributions from CAL-ACCESS (state PAC/IE filings) and NetFile (local
              council candidate filings).
            </li>
            <li>
              <strong>Entity matching:</strong> Donor names, employers, and entities mentioned in
              agenda items are normalized and compared. Employer cross-referencing catches indirect
              connections.
            </li>
            <li>
              <strong>Confidence scoring:</strong> Matches are scored by confidence across three
              tiers: Strong (&ge;85%), Moderate (&ge;70%), and Low (&ge;50%). Flags below 50%
              are tracked internally only.
            </li>
            <li>
              <strong>False positive reduction:</strong> Government entity donors, sitting council
              member names, generic employers, and duplicate filings are automatically filtered.
            </li>
          </ol>
        </div>
      </section>
    </OperatorGate>
  )
}

function TierCard({
  tier,
  label,
  color,
  description,
}: {
  tier: number
  label: string
  color: string
  description: string
}) {
  return (
    <div className={`rounded-lg border p-3 ${color}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs font-bold text-slate-500">TIER {tier}</span>
        <span className="font-semibold text-slate-800 text-sm">{label}</span>
      </div>
      <p className="text-sm text-slate-600">{description}</p>
    </div>
  )
}
