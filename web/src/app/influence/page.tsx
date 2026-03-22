import Link from 'next/link'
import type { Metadata } from 'next'
import { getAllFinancialConnectionSummaries } from '@/lib/queries'
import { CampaignFinanceDisclaimer } from '@/components/InfluenceDisclaimer'
import EntityTypeIndicator from '@/components/EntityTypeIndicator'
import ConfidenceBadge from '@/components/ConfidenceBadge'
import OperatorGate from '@/components/OperatorGate'
import { CONFIDENCE_STRONG, CONFIDENCE_MODERATE } from '@/lib/thresholds'

export const revalidate = 3600

export const metadata: Metadata = {
  title: 'Influence Map — Richmond Common',
  description: 'Campaign finance connections between contributors and council members, organized by official.',
}

function confidenceBreakdown(flags: Array<{ confidence: number }>) {
  let strong = 0, moderate = 0, low = 0
  for (const f of flags) {
    if (f.confidence >= CONFIDENCE_STRONG) strong++
    else if (f.confidence >= CONFIDENCE_MODERATE) moderate++
    else low++
  }
  return { strong, moderate, low }
}

export default async function InfluenceIndexPage() {
  return (
    <OperatorGate>
      <InfluenceIndexContent />
    </OperatorGate>
  )
}

async function InfluenceIndexContent() {
  const summaries = await getAllFinancialConnectionSummaries()

  const totalRecords = summaries.reduce((sum, s) => sum + s.total_flags, 0)
  const officialsWithRecords = summaries.filter(s => s.total_flags > 0).length

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-civic-navy">Influence Map</h1>
        <p className="text-sm text-slate-600 mt-2 max-w-2xl leading-relaxed">
          Campaign finance connections between contributors and Richmond City Council
          members. Each record cross-references public contribution filings against
          agenda items the official voted on.
        </p>
        <CampaignFinanceDisclaimer />
      </header>

      {/* Summary stats */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 mb-8">
        <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
          <p className="text-2xl font-bold text-civic-navy">{totalRecords}</p>
          <p className="text-xs text-slate-500 mt-1">Total Records</p>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
          <p className="text-2xl font-bold text-civic-navy">{officialsWithRecords}</p>
          <p className="text-xs text-slate-500 mt-1">Officials with Records</p>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4 text-center hidden sm:block">
          <p className="text-2xl font-bold text-civic-navy">
            {summaries.reduce((sum, s) => {
              const b = confidenceBreakdown(s.flags)
              return sum + b.strong
            }, 0)}
          </p>
          <p className="text-xs text-slate-500 mt-1">Strong Confidence</p>
        </div>
      </div>

      {/* Official cards */}
      {summaries.length === 0 ? (
        <div className="bg-slate-50 border border-slate-200 rounded-lg p-6 text-center">
          <p className="text-sm text-slate-600">
            No campaign finance connections identified at the published confidence threshold.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {summaries.map(s => {
            const breakdown = confidenceBreakdown(s.flags)
            const topTypes = Object.entries(s.flag_type_breakdown)
              .sort(([, a], [, b]) => b - a)
              .slice(0, 3)

            return (
              <Link
                key={s.official_id}
                href={`/council/${s.official_slug}`}
                className="block bg-white border border-slate-200 rounded-lg p-4 hover:bg-slate-50 hover:border-slate-300 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <EntityTypeIndicator entityType="official" />
                      <h2 className="text-base font-semibold text-slate-900">
                        {s.official_name}
                      </h2>
                    </div>

                    {/* Record count + vote pattern */}
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2 text-xs text-slate-500">
                      <span className="font-medium text-slate-700">
                        {s.total_flags} {s.total_flags === 1 ? 'record' : 'records'}
                      </span>
                      {s.voted_in_favor > 0 && (
                        <span>Voted in favor on {s.voted_in_favor} contested {s.voted_in_favor === 1 ? 'item' : 'items'}</span>
                      )}
                      {s.abstained > 0 && (
                        <span>Abstained on {s.abstained} {s.abstained === 1 ? 'item' : 'items'}</span>
                      )}
                    </div>

                    {/* Confidence breakdown */}
                    <div className="flex flex-wrap items-center gap-2 mt-2">
                      {breakdown.strong > 0 && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-red-50 text-red-700 border border-red-200">
                          {breakdown.strong} strong
                        </span>
                      )}
                      {breakdown.moderate > 0 && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-amber-50 text-amber-700 border border-amber-200">
                          {breakdown.moderate} moderate
                        </span>
                      )}
                      {breakdown.low > 0 && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-green-50 text-green-700 border border-green-200">
                          {breakdown.low} low
                        </span>
                      )}
                    </div>

                    {/* Top flag types */}
                    {topTypes.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {topTypes.map(([type, count]) => (
                          <span key={type} className="text-[10px] text-slate-400">
                            {type.replace(/_/g, ' ')} ({count})
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  <span className="text-slate-400 text-sm ml-4 mt-1 shrink-0">→</span>
                </div>
              </Link>
            )
          })}
        </div>
      )}

      {/* Methodology link */}
      <div className="border-t border-slate-200 pt-6 mt-8 text-center">
        <Link
          href="/influence/methodology"
          className="text-sm text-civic-navy hover:underline"
        >
          How this data is collected and analyzed →
        </Link>
      </div>
    </div>
  )
}
