'use client'

import { useState } from 'react'
import type { CandidateDonorsByCycle, CandidateTopDonor } from '@/lib/types'

export default function DonorSection({ donors }: { donors: CandidateDonorsByCycle }) {
  const [cycleOpen, setCycleOpen] = useState(false)
  const [priorOpen, setPriorOpen] = useState(false)

  const hasCycle = donors.cycleDonors.length > 0
  const hasPrior = donors.priorDonors.length > 0

  return (
    <div className="space-y-2">
      {hasCycle && (
        <div className="rounded-lg border border-slate-200/60 overflow-hidden">
          <button
            onClick={() => setCycleOpen(!cycleOpen)}
            className="w-full flex items-center justify-between px-4 py-3 text-sm hover:bg-white/60 transition-colors"
            aria-expanded={cycleOpen}
          >
            <span className="flex items-center gap-2">
              <ChevronIcon open={cycleOpen} />
              <span className="font-medium text-civic-navy">
                Donors this election cycle
              </span>
              <span className="text-xs text-slate-400 tabular-nums">
                ({donors.cycleDonors.length})
              </span>
            </span>
            <span className="text-xs text-slate-400">
              {donors.cycleLabel}
            </span>
          </button>
          {cycleOpen && (
            <DonorList donors={donors.cycleDonors} />
          )}
        </div>
      )}

      {hasPrior && (
        <div className="rounded-lg border border-slate-200/60 overflow-hidden">
          <button
            onClick={() => setPriorOpen(!priorOpen)}
            className="w-full flex items-center justify-between px-4 py-3 text-sm hover:bg-white/60 transition-colors"
            aria-expanded={priorOpen}
          >
            <span className="flex items-center gap-2">
              <ChevronIcon open={priorOpen} />
              <span className="font-medium text-slate-600">
                Previous election cycles
              </span>
              <span className="text-xs text-slate-400 tabular-nums">
                ({donors.priorDonors.length})
              </span>
            </span>
          </button>
          {priorOpen && (
            <DonorList donors={donors.priorDonors} />
          )}
        </div>
      )}
    </div>
  )
}

function DonorList({ donors }: { donors: CandidateTopDonor[] }) {
  return (
    <div className="px-4 pb-4 pt-1">
      <div className="space-y-0.5">
        {donors.map((donor, i) => (
          <div
            key={donor.donor_name}
            className={`flex items-start justify-between text-sm py-2 px-2 rounded ${
              i % 2 === 0 ? 'bg-white/40' : ''
            }`}
          >
            <div className="min-w-0">
              <span className="font-medium text-slate-700">{donor.donor_name}</span>
              {donor.employer && (
                <span className="text-slate-400 text-xs ml-1.5">
                  {donor.employer}
                </span>
              )}
            </div>
            <div className="text-right whitespace-nowrap shrink-0 ml-4">
              <span className="font-semibold text-civic-navy tabular-nums">
                ${donor.total_contributed.toLocaleString('en-US', { maximumFractionDigits: 0 })}
              </span>
              {donor.contribution_count > 1 && (
                <span className="text-slate-400 text-xs ml-1">
                  ({donor.contribution_count}x)
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
      <p className="text-[10px] text-slate-400 mt-3 px-2">
        Source: NetFile public filings &middot; Excludes government entity transfers
      </p>
    </div>
  )
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 16 16"
      fill="none"
      className={`transition-transform duration-200 shrink-0 ${open ? 'rotate-90' : ''}`}
      aria-hidden="true"
    >
      <path
        d="M6 4l4 4-4 4"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
