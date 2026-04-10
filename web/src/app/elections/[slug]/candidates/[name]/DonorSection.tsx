'use client'

import { useState } from 'react'
import type { CandidateDonorsByCycle, CandidateTopDonor } from '@/lib/types'

export default function DonorSection({ donors }: { donors: CandidateDonorsByCycle }) {
  const [cycleOpen, setCycleOpen] = useState(false)
  const [priorOpen, setPriorOpen] = useState(false)

  const hasCycle = donors.cycleDonors.length > 0
  const hasPrior = donors.priorDonors.length > 0

  return (
    <div className="space-y-3">
      {hasCycle && (
        <div className="border border-slate-200 rounded-lg">
          <button
            onClick={() => setCycleOpen(!cycleOpen)}
            className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-civic-navy hover:bg-slate-50 transition-colors rounded-lg"
            aria-expanded={cycleOpen}
          >
            <span>
              Donors this election cycle ({donors.cycleDonors.length})
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
        <div className="border border-slate-200 rounded-lg">
          <button
            onClick={() => setPriorOpen(!priorOpen)}
            className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors rounded-lg"
            aria-expanded={priorOpen}
          >
            <span>
              Previous election cycles ({donors.priorDonors.length})
            </span>
            <ChevronIcon open={priorOpen} />
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
    <div className="px-4 pb-4 space-y-1.5">
      {donors.map((donor) => (
        <div
          key={donor.donor_name}
          className="flex items-start justify-between text-sm text-slate-600 gap-3"
        >
          <div className="min-w-0">
            <span className="font-medium text-slate-700">{donor.donor_name}</span>
            {donor.employer && (
              <span className="text-slate-400 ml-1">({donor.employer})</span>
            )}
          </div>
          <div className="text-right whitespace-nowrap shrink-0">
            <span className="font-medium text-civic-navy">
              ${donor.total_contributed.toLocaleString('en-US', { maximumFractionDigits: 0 })}
            </span>
            {donor.contribution_count > 1 && (
              <span className="text-slate-400 ml-1">
                ({donor.contribution_count}x)
              </span>
            )}
          </div>
        </div>
      ))}
      <p className="text-[10px] text-slate-400 mt-2">
        Source: NetFile &middot; Excludes government entity transfers
      </p>
    </div>
  )
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      className={`transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
      aria-hidden="true"
    >
      <path
        d="M4 6l4 4 4-4"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
