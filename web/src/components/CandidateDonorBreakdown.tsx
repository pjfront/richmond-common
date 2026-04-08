'use client'

import { useState } from 'react'
import type { CandidateTopDonor, ContributionBreakdown } from '@/lib/types'

interface CandidateDonorBreakdownProps {
  topDonors: CandidateTopDonor[]
  breakdown: ContributionBreakdown
  totalRaised: number
}

const BUCKETS = [
  { key: 'small' as const, label: 'Under $100' },
  { key: 'medium' as const, label: '$100\u2013$499' },
  { key: 'large' as const, label: '$500\u2013$999' },
  { key: 'major' as const, label: '$1,000+' },
]

export default function CandidateDonorBreakdown({
  topDonors,
  breakdown,
  totalRaised,
}: CandidateDonorBreakdownProps) {
  const [expanded, setExpanded] = useState(false)
  const [showTable, setShowTable] = useState(false)

  if (topDonors.length === 0 && breakdown.total_count === 0) return null

  // Narrative breakdown: largest bucket as percentage
  const breakdownNarrative = buildBreakdownNarrative(breakdown)

  return (
    <div className="mt-3">
      {/* Contribution size narrative */}
      {breakdownNarrative && (
        <div className="flex items-center gap-2 mt-1">
          <p className="text-xs text-slate-500">{breakdownNarrative}</p>
          {breakdown.total_count > 0 && (
            <button
              onClick={() => setShowTable(!showTable)}
              className="text-[10px] text-civic-navy hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-civic-navy/40 rounded"
              aria-expanded={showTable}
            >
              {showTable ? 'Hide' : 'View'} breakdown
            </button>
          )}
        </div>
      )}

      {/* Accessible table view — satisfies C2 (chart table toggle) and A6 (screen reader access) */}
      {showTable && breakdown.total_count > 0 && (
        <table className="mt-2 w-full text-xs border-collapse">
          <caption className="sr-only">Contribution size breakdown</caption>
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200">
              <th className="py-1 pr-3 font-medium">Size</th>
              <th className="py-1 pr-3 font-medium text-right">Count</th>
              <th className="py-1 font-medium text-right">Share</th>
            </tr>
          </thead>
          <tbody>
            {BUCKETS.map(({ key, label }) => {
              const count = breakdown[key]
              const pct = breakdown.total_count > 0
                ? Math.round((count / breakdown.total_count) * 100)
                : 0
              return (
                <tr key={key} className="border-b border-slate-100 last:border-0">
                  <td className="py-1 pr-3 text-slate-700">{label}</td>
                  <td className="py-1 pr-3 text-right text-slate-600">{count}</td>
                  <td className="py-1 text-right text-slate-600">{pct}%</td>
                </tr>
              )
            })}
            <tr className="border-t border-slate-300 font-medium">
              <td className="py-1 pr-3 text-slate-700">Total</td>
              <td className="py-1 pr-3 text-right text-slate-700">{breakdown.total_count}</td>
              <td className="py-1 text-right text-slate-700">100%</td>
            </tr>
          </tbody>
        </table>
      )}

      {/* Expandable top donors */}
      {topDonors.length > 0 && (
        <div className="mt-2">
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-civic-navy hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-civic-navy/40 rounded"
            aria-expanded={expanded}
          >
            {expanded ? 'Hide' : 'Show'} top donors ({topDonors.length})
          </button>

          {expanded && (
            <div className="mt-2 space-y-1.5">
              {topDonors.map((donor) => (
                <div
                  key={donor.donor_name}
                  className="flex items-start justify-between text-xs text-slate-600 gap-2"
                >
                  <div className="min-w-0">
                    <span className="font-medium text-slate-700">
                      {donor.donor_name}
                    </span>
                    {donor.employer && (
                      <span className="text-slate-400 ml-1">
                        ({donor.employer})
                      </span>
                    )}
                  </div>
                  <div className="text-right whitespace-nowrap shrink-0">
                    <span className="font-medium text-civic-navy">
                      ${donor.total_contributed.toLocaleString('en-US', {
                        maximumFractionDigits: 0,
                      })}
                    </span>
                    {donor.contribution_count > 1 && (
                      <span className="text-slate-400 ml-1">
                        ({donor.contribution_count}x)
                      </span>
                    )}
                  </div>
                </div>
              ))}
              <p className="text-[10px] text-slate-400 mt-1">
                Source: NetFile · Excludes government entity transfers
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function buildBreakdownNarrative(breakdown: ContributionBreakdown): string | null {
  if (breakdown.total_count === 0) return null

  const pcts = {
    small: Math.round((breakdown.small / breakdown.total_count) * 100),
    medium: Math.round((breakdown.medium / breakdown.total_count) * 100),
    large: Math.round((breakdown.large / breakdown.total_count) * 100),
    major: Math.round((breakdown.major / breakdown.total_count) * 100),
  }

  // Lead with the most common bucket
  const buckets = [
    { label: 'under $100', pct: pcts.small },
    { label: '$100\u2013$499', pct: pcts.medium },
    { label: '$500\u2013$999', pct: pcts.large },
    { label: '$1,000+', pct: pcts.major },
  ].filter((b) => b.pct > 0)

  if (buckets.length === 0) return null

  buckets.sort((a, b) => b.pct - a.pct)
  const top = buckets[0]

  return `${top.pct}% of contributions were ${top.label}.`
}
