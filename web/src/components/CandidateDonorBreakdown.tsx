'use client'

import { useState } from 'react'
import type { CandidateTopDonor, ContributionBreakdown } from '@/lib/types'

interface CandidateDonorBreakdownProps {
  topDonors: CandidateTopDonor[]
  breakdown: ContributionBreakdown
  totalRaised: number
}

export default function CandidateDonorBreakdown({
  topDonors,
  breakdown,
  totalRaised,
}: CandidateDonorBreakdownProps) {
  const [expanded, setExpanded] = useState(false)

  if (topDonors.length === 0 && breakdown.total_count === 0) return null

  // Narrative breakdown: largest bucket as percentage
  const breakdownNarrative = buildBreakdownNarrative(breakdown)

  return (
    <div className="mt-3">
      {/* Contribution size narrative */}
      {breakdownNarrative && (
        <p className="text-xs text-slate-500 mt-1">{breakdownNarrative}</p>
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
