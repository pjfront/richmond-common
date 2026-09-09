import Link from 'next/link'
import type { ElectionCandidate } from '@/lib/types'

export type CandidateIdentity = Pick<ElectionCandidate, 'id' | 'candidate_name' | 'office_sought' | 'is_incumbent' | 'official_id'>
import { officialToSlug } from '@/lib/queries/_shared'
import OperatorGate from './OperatorGate'

/** A dated source summary replaces unreconciled legacy financial statistics. */
export interface CandidateFinanceCoverage {
  kind: 'source-checked-summary'
  href: string
  scopeNote: string
}

export type CandidateFinanceCoverageById = Readonly<Record<string, CandidateFinanceCoverage>>

export default function CandidateCard({
  candidate,
  electionSlug,
  financeCoverage,
}: {
  candidate: CandidateIdentity
  electionSlug?: string
  financeCoverage?: CandidateFinanceCoverage
}) {
  const anchorId = candidate.candidate_name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')

  const canonicalCandidateHref = electionSlug
    ? `/elections/${encodeURIComponent(electionSlug)}#${anchorId}`
    : null

  return (
    <article
      id={anchorId}
      aria-labelledby={`${anchorId}-name`}
      tabIndex={-1}
      className="bg-white border border-slate-100 rounded-lg p-4 scroll-mt-20"
    >
      <div className="flex items-start justify-between">
        <div>
          <h3
            id={`${anchorId}-name`}
            className="text-base font-semibold text-civic-navy"
          >
            {electionSlug && canonicalCandidateHref ? (
              <OperatorGate
                fallback={(
                  <Link
                    href={canonicalCandidateHref}
                    aria-label={`${candidate.candidate_name} on this election page`}
                    className="inline-flex min-h-11 items-center hover:underline"
                  >
                    {candidate.candidate_name}
                  </Link>
                )}
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

      {financeCoverage && (
        <div className="mt-3 text-sm leading-relaxed text-slate-600">
          <p>See the campaign&apos;s reported donations, cash balance and spending in the dated summary.</p>
          <p className="mt-2">{financeCoverage.scopeNote}</p>
          <Link href={financeCoverage.href} className="mt-2 inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4">
            Read the dated campaign-money summary &rarr;
          </Link>
        </div>
      )}
    </article>
  )
}
