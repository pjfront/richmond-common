import Link from 'next/link'
import type { Metadata } from 'next'
import { getAllFinancialConnectionSummaries } from '@/lib/queries'
import FinancialConnectionsAllTable, { type ConnectionTableRow } from '@/components/FinancialConnectionsAllTable'
import OperatorGate from '@/components/OperatorGate'

// Operator-only page — skip static prerendering, render on demand
export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Financial Connections',
  description: 'Cross-reference of council agenda items against campaign contributions and financial disclosures for all Richmond officials.',
}

export default async function FinancialConnectionsPage() {
  const summaries = await getAllFinancialConnectionSummaries()

  const totalFlags = summaries.reduce((sum, s) => sum + s.total_flags, 0)
  const officialsWithFlags = summaries.filter((s) => s.total_flags > 0).length
  const totalVotedInFavor = summaries.reduce((sum, s) => sum + s.voted_in_favor, 0)

  // Flatten all flags into rows with official context for the table.
  // Strip heavy fields (description, evidence) to reduce RSC payload size.
  // These are only needed when a row is expanded, loaded on-demand by the client.
  const allRows = summaries.flatMap((s) =>
    s.flags.map((f) => ({
      id: f.id,
      flag_type: f.flag_type,
      confidence: f.confidence,
      meeting_id: f.meeting_id,
      meeting_date: f.meeting_date,
      agenda_item_id: f.agenda_item_id,
      agenda_item_title: f.agenda_item_title,
      agenda_item_number: f.agenda_item_number,
      agenda_item_category: f.agenda_item_category,
      vote_choice: f.vote_choice,
      motion_result: f.motion_result,
      is_unanimous: f.is_unanimous,
      official_name: s.official_name,
      official_slug: s.official_slug,
    }))
  )

  // Strip flags from summaries before sending to client (stats cards only need aggregates)
  const summaryStats = summaries.map(({ flags: _flags, ...rest }) => rest)

  // Most common flag type
  const typeCount: Record<string, number> = {}
  for (const s of summaries) {
    for (const [type, count] of Object.entries(s.flag_type_breakdown)) {
      typeCount[type] = (typeCount[type] ?? 0) + count
    }
  }
  const topType = Object.entries(typeCount).sort(([, a], [, b]) => b - a)[0]
  const topTypeName = topType
    ? topType[0].replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
    : 'None'

  return (
    <OperatorGate fallback={
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-16 text-center">
        <h1 className="text-2xl font-bold text-civic-navy mb-3">Financial Connections</h1>
        <p className="text-slate-600">This feature is under development and not yet available to the public.</p>
      </div>
    }>
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-civic-navy">Financial Connections</h1>
        <p className="text-slate-600 mt-2 max-w-3xl">
          Cross-reference of agenda items against campaign contributions and financial disclosures,
          correlated with voting outcomes. This view aggregates data from all{' '}
          <Link href="/reports" className="text-civic-navy-light underline">
            per-meeting transparency reports
          </Link>.
        </p>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
        <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
          <p className="text-2xl font-bold text-civic-navy">{totalFlags}</p>
          <p className="text-xs text-slate-500 mt-1">Total Connections</p>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
          <p className="text-2xl font-bold text-civic-navy">{officialsWithFlags}</p>
          <p className="text-xs text-slate-500 mt-1">Officials with Flags</p>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
          <p className="text-2xl font-bold text-vote-aye">{totalVotedInFavor}</p>
          <p className="text-xs text-slate-500 mt-1">Voted Aye (Contested)</p>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
          <p className="text-sm font-semibold text-civic-navy">{topTypeName}</p>
          <p className="text-xs text-slate-500 mt-1">Most Common Type</p>
        </div>
      </div>

      {/* Per-official breakdown */}
      {summaryStats.length > 0 && (
        <div className="mb-8">
          <h2 className="text-lg font-semibold text-slate-800 mb-3">By Official</h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {summaryStats.map((s) => (
              <Link
                key={s.official_id}
                href={`/council/${s.official_slug}`}
                className="bg-white rounded-lg border border-slate-200 p-3 hover:border-civic-navy-light transition-colors"
              >
                <p className="font-medium text-slate-800">{s.official_name}</p>
                <div className="flex gap-3 mt-1 text-xs text-slate-500">
                  <span>{s.total_flags} flags</span>
                  {s.voted_in_favor > 0 && (
                    <span className="text-vote-aye">{s.voted_in_favor} aye</span>
                  )}
                  {s.voted_against > 0 && (
                    <span className="text-vote-nay">{s.voted_against} nay</span>
                  )}
                  {s.abstained > 0 && (
                    <span className="text-vote-abstain">{s.abstained} abstain</span>
                  )}
                </div>
              </Link>
            ))}
          </div>
          <p className="text-[11px] text-slate-400 mt-2">
            Aye/nay counts reflect contested (non-unanimous) votes only.
          </p>
        </div>
      )}

      {/* All connections table */}
      <section>
        <h2 className="text-lg font-semibold text-slate-800 mb-3">All Connections</h2>
        {allRows.length === 0 ? (
          <div className="bg-green-50 border border-green-200 rounded-lg p-4">
            <p className="text-sm text-green-700">
              No financial connections have been identified across any officials.
            </p>
          </div>
        ) : (
          <FinancialConnectionsAllTable rows={allRows} />
        )}
      </section>

      {/* Methodology note */}
      <div className="mt-8 bg-slate-50 rounded-lg border border-slate-200 p-4">
        <h3 className="font-semibold text-slate-700 mb-2">About This Data</h3>
        <p className="text-sm text-slate-600 leading-relaxed">
          Financial connections are identified by cross-referencing agenda item text against campaign
          contributions from CAL-ACCESS (PAC/IE committees) and NetFile (local council candidate
          committees), plus Form 700 economic interest disclosures. Each connection includes the
          official&apos;s vote on the related agenda item when a recorded vote exists. A financial
          connection does not imply wrongdoing.
        </p>
        <Link
          href="/about"
          className="text-sm text-civic-navy-light hover:text-civic-navy inline-block mt-2"
        >
          Learn more about our methodology &rarr;
        </Link>
      </div>
    </div>
    </OperatorGate>
  )
}
