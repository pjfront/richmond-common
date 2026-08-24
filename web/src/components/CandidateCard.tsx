import Link from 'next/link'
import type { CandidateFundraisingDetail } from '@/lib/types'
import { officialToSlug } from '@/lib/queries'
import CandidateContributionBuckets from './CandidateContributionBuckets'
import OperatorGate from './OperatorGate'

/** Format a date as "Mon YYYY" */
function fmtDate(d: string): string {
  return new Date(d + 'T00:00:00').toLocaleDateString('en-US', {
    month: 'short',
    year: 'numeric',
  })
}

export default function CandidateCard({
  candidate,
  electionSlug,
}: {
  candidate: CandidateFundraisingDetail
  electionSlug?: string
}) {
  const hasCycleData = candidate.contribution_count > 0
  const hasLifetimeOnly = !hasCycleData && candidate.lifetime_raised > 0
  const hasAnyData = hasCycleData || hasLifetimeOnly
  const showLifetimeLine = candidate.lifetime_raised > candidate.total_raised

  const anchorId = candidate.candidate_name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')

  return (
    <div
      id={anchorId}
      className="bg-white border border-slate-100 rounded-lg p-4 scroll-mt-20"
    >
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-base font-semibold text-civic-navy">
            {electionSlug ? (
              <OperatorGate
                fallback={<span>{candidate.candidate_name}</span>}
              >
                <Link
                  href={`/elections/${electionSlug}/candidates/${anchorId}`}
                  className="inline-flex min-h-11 items-center hover:underline"
                >
                  {candidate.candidate_name}
                </Link>
              </OperatorGate>
            ) : (
              candidate.candidate_name
            )}
          </h3>
          <div className="flex items-center gap-2 mt-1">
            {candidate.is_incumbent && (
              <span className="inline-block px-2 py-0.5 text-xs font-medium bg-civic-navy/10 text-civic-navy rounded">
                Incumbent
              </span>
            )}
            {candidate.is_incumbent && candidate.official_id && (
              <Link
                href={`/council/${officialToSlug(candidate.candidate_name)}`}
                className="text-xs text-civic-navy hover:underline"
              >
                View voting record &rarr;
              </Link>
            )}
          </div>
        </div>
      </div>

      {/* Campaign finance display. Graduated to public 2026-05-22 (D56b
          verification PR). Headline total_raised is sourced from each
          candidate's own Form 460 cover (queries/elections.ts line ~619).
          The bucket grid below is shown only when the DB contribution rows
          add up to the form headline within $1 — see bucket_grid_consistent
          in queries/elections.ts and the methodology page for the case
          where it doesn't (Form 497 late-filings, paper-filing reconciliation). */}
      {hasCycleData ? (
        <div className="mt-3 text-sm text-slate-600 leading-relaxed">
          <p>
            Raised{' '}
            <span className="font-medium text-civic-navy">
              $
              {candidate.total_raised.toLocaleString('en-US', {
                maximumFractionDigits: 0,
              })}
            </span>{' '}
            from{' '}
            <span className="font-medium">
              {candidate.donor_count.toLocaleString()}
            </span>{' '}
            donor{candidate.donor_count !== 1 ? 's' : ''} for this election.
          </p>
          <p className="text-xs text-slate-500 mt-1">
            {candidate.contribution_count} contributions · Average $
            {candidate.avg_contribution.toLocaleString('en-US', {
              maximumFractionDigits: 0,
            })}
            {' · '}Largest $
            {candidate.largest_contribution.toLocaleString('en-US', {
              maximumFractionDigits: 0,
            })}
          </p>

          {showLifetimeLine && candidate.earliest_contribution && (
            <p className="text-xs text-slate-400 mt-2">
              Committee has raised $
              {candidate.lifetime_raised.toLocaleString('en-US', {
                maximumFractionDigits: 0,
              })}{' '}
              total since {fmtDate(candidate.earliest_contribution)}.
            </p>
          )}

          {candidate.bucket_grid_consistent ? (
            <CandidateContributionBuckets
              matrix={candidate.contribution_matrix}
              firstName={candidate.candidate_name.split(' ')[0]}
            />
          ) : (
            <p className="mt-3 text-xs text-slate-500 italic">
              Breakdown by donor type and amount isn&apos;t shown for this
              candidate yet — the contributions we have on file don&apos;t
              add up to the headline total above. Usually that&apos;s a
              late-filed disclosure or a paper filing still being processed.{' '}
              <Link
                href="/elections/methodology"
                className="text-civic-navy hover:underline not-italic"
              >
                More on this
              </Link>
              .
            </p>
          )}
        </div>
      ) : hasLifetimeOnly ? (
        <div className="mt-3 text-sm text-slate-500">
          <p>No fundraising recorded for this election.</p>
          {candidate.earliest_contribution && candidate.latest_contribution && (
            <p className="text-xs text-slate-400 mt-1">
              Committee raised $
              {candidate.lifetime_raised.toLocaleString('en-US', {
                maximumFractionDigits: 0,
              })}{' '}
              in prior elections ({fmtDate(candidate.earliest_contribution)} –{' '}
              {fmtDate(candidate.latest_contribution)}).
            </p>
          )}
        </div>
      ) : hasAnyData ? null : (
        <p className="mt-3 text-sm text-slate-400 italic">
          No campaign finance filings linked yet.
        </p>
      )}
    </div>
  )
}
