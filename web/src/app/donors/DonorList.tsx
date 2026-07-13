/**
 * Donor list component — shared card grid for /donors index.
 *
 * Pattern: mirrors OrgList from S28.3 (I164).
 */

import Link from 'next/link'
import type { DonorProfile } from '@/lib/types'

function fmt(n: number): string {
  return n.toLocaleString('en-US', { maximumFractionDigits: 0 })
}

function fmtDate(iso: string): string {
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', {
    month: 'short',
    year: 'numeric',
  })
}

function DonorCard({ donor }: { donor: DonorProfile }) {
  return (
    <Link
      href={`/donors/${donor.slug}`}
      className="block border border-slate-200 rounded-lg p-5 hover:border-civic-navy/40 hover:bg-civic-navy/[0.01] transition-colors group"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold text-civic-navy group-hover:text-civic-navy-light truncate">
            {donor.display_name}
          </h2>

          {donor.employer && (
            <p className="text-sm text-slate-500 mt-0.5">
              {donor.employer}
              {donor.occupation ? ` · ${donor.occupation}` : ''}
            </p>
          )}

          <p className="text-sm text-slate-600 mt-2 leading-relaxed">
            <strong>${fmt(donor.total_contributed)}</strong> in tracked
            contributions
            {donor.earliest_contribution_date &&
              donor.latest_contribution_date && (
                <>
                  {' '}
                  from {fmtDate(donor.earliest_contribution_date)} to{' '}
                  {fmtDate(donor.latest_contribution_date)}
                </>
              )}
            {donor.recipient_count > 0 && (
              <>
                {' '}
                across <strong>{donor.recipient_count}</strong> recipient
                {donor.recipient_count === 1 ? '' : 's'}
              </>
            )}
            .
          </p>
        </div>

        <div className="shrink-0 self-center">
          <span
            aria-hidden="true"
            className="text-slate-300 group-hover:text-civic-navy-light transition-colors text-xl"
          >
            →
          </span>
        </div>
      </div>
    </Link>
  )
}

interface DonorListProps {
  donors: DonorProfile[]
}

export default function DonorList({ donors }: DonorListProps) {
  if (donors.length === 0) {
    return (
      <div className="border border-slate-200 rounded-lg p-10 text-center">
        <p className="text-slate-500">
          No individual donor data available yet. Entity typing is running —
          check back soon.
        </p>
      </div>
    )
  }

  return (
    <>
      <header className="mb-6">
        <h1 className="text-3xl font-bold text-civic-navy">Individual Donors</h1>
        <p className="text-slate-600 mt-2 leading-relaxed max-w-3xl">
          Individual donors who have contributed at least $5,000 in total across
          all tracked Richmond political campaigns. All data is from public
          campaign-finance filings.
        </p>
      </header>

      <p className="text-xs text-slate-500 mb-4">
        {donors.length} donor{donors.length === 1 ? '' : 's'} above the $5,000
        threshold
      </p>

      <div className="space-y-3">
        {donors.map((donor) => (
          <DonorCard key={donor.slug} donor={donor} />
        ))}
      </div>
    </>
  )
}
