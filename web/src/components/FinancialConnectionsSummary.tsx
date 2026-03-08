import type { OfficialConnectionSummary } from '@/lib/types'

function formatFlagType(type: string): string {
  return type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export default function FinancialConnectionsSummary({
  summary,
}: {
  summary: OfficialConnectionSummary
}) {
  const { total_flags, voted_in_favor, voted_against, abstained, absent_for, no_vote_recorded, flag_type_breakdown } = summary

  const votedTotal = voted_in_favor + voted_against + abstained + absent_for
  const favorPct = votedTotal > 0 ? Math.round((voted_in_favor / votedTotal) * 100) : 0

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      {/* Top stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
        <div className="text-center">
          <p className="text-2xl font-bold text-civic-navy">{total_flags}</p>
          <p className="text-xs text-slate-500 mt-0.5">Financial Connections</p>
        </div>
        <div className="text-center">
          <p className="text-2xl font-bold text-vote-aye">{voted_in_favor}</p>
          <p className="text-xs text-slate-500 mt-0.5">
            Voted in Favor{votedTotal > 0 && ` (${favorPct}%)`}
          </p>
        </div>
        <div className="text-center">
          <p className="text-2xl font-bold text-vote-nay">{voted_against}</p>
          <p className="text-xs text-slate-500 mt-0.5">Voted Against</p>
        </div>
        <div className="text-center">
          <p className="text-2xl font-bold text-vote-abstain">
            {abstained + absent_for}
          </p>
          <p className="text-xs text-slate-500 mt-0.5">
            Abstained / Absent
          </p>
        </div>
      </div>

      {/* Flag type breakdown */}
      {Object.keys(flag_type_breakdown).length > 0 && (
        <div className="border-t border-slate-100 pt-3">
          <p className="text-xs text-slate-400 mb-2">By flag type</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(flag_type_breakdown)
              .sort(([, a], [, b]) => b - a)
              .map(([type, count]) => (
                <span
                  key={type}
                  className="inline-flex items-center gap-1 text-xs bg-slate-100 text-slate-600 px-2 py-1 rounded"
                >
                  {formatFlagType(type)}
                  <span className="font-semibold">{count}</span>
                </span>
              ))}
          </div>
        </div>
      )}

      {/* No vote recorded note */}
      {no_vote_recorded > 0 && (
        <p className="text-xs text-slate-400 mt-2">
          {no_vote_recorded} flag{no_vote_recorded !== 1 ? 's' : ''} without a
          recorded individual vote (e.g., consent calendar items).
        </p>
      )}
    </div>
  )
}
