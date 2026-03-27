import Link from 'next/link'
import type { Metadata } from 'next'
import { getElectionWithCandidates, getElectionFundraisingSummary } from '@/lib/queries'
import OperatorGate from '@/components/OperatorGate'
import type { CandidateFundraising } from '@/lib/types'

export const dynamic = 'force-dynamic'
export const revalidate = 3600

interface PageProps {
  params: Promise<{ id: string }>
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { id } = await params
  const election = await getElectionWithCandidates(id)
  const name = election?.election_name || 'Election Detail'
  return {
    title: `${name} — Richmond Commons`,
    description: `Candidates and campaign finance data for ${name}.`,
  }
}

export default async function ElectionDetailPage({ params }: PageProps) {
  return (
    <OperatorGate>
      <ElectionDetailContent params={params} />
    </OperatorGate>
  )
}

async function ElectionDetailContent({ params }: PageProps) {
  const { id } = await params
  const [election, fundraising] = await Promise.all([
    getElectionWithCandidates(id),
    getElectionFundraisingSummary(id),
  ])

  if (!election) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <p className="text-slate-500">Election not found.</p>
        <Link href="/influence/elections" className="text-civic-navy hover:underline text-sm mt-4 inline-block">
          Back to elections
        </Link>
      </div>
    )
  }

  const date = new Date(election.election_date + 'T00:00:00')
  const formattedDate = date.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
  const isUpcoming = date >= new Date()
  const daysUntil = Math.ceil(
    (date.getTime() - Date.now()) / (1000 * 60 * 60 * 24),
  )

  const totalRaised = fundraising.reduce((sum, c) => sum + c.total_raised, 0)
  const totalContributions = fundraising.reduce(
    (sum, c) => sum + c.contribution_count,
    0,
  )

  // Group candidates by office
  const byOffice = new Map<string, CandidateFundraising[]>()
  for (const c of fundraising) {
    const existing = byOffice.get(c.office_sought) || []
    existing.push(c)
    byOffice.set(c.office_sought, existing)
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <Link
        href="/influence/elections"
        className="text-sm text-civic-navy hover:underline mb-4 inline-block"
      >
        ← All elections
      </Link>

      <header className="mb-8">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-3xl font-bold text-civic-navy">
              {election.election_name || `${election.election_type} Election`}
            </h1>
            <p className="text-slate-600 mt-1">{formattedDate}</p>
            {election.jurisdiction && (
              <p className="text-sm text-slate-400 mt-1">{election.jurisdiction}</p>
            )}
          </div>
          <span
            className={`inline-block px-3 py-1 text-sm font-medium rounded ${
              election.election_type === 'primary'
                ? 'bg-blue-50 text-blue-700'
                : election.election_type === 'general'
                  ? 'bg-green-50 text-green-700'
                  : 'bg-slate-50 text-slate-600'
            }`}
          >
            {election.election_type}
          </span>
        </div>

        {isUpcoming && daysUntil > 0 && (
          <p className="text-sm text-civic-amber font-medium mt-3">
            {daysUntil} days until election day
          </p>
        )}

        {election.filing_deadline && (
          <p className="text-xs text-slate-500 mt-2">
            Filing deadline:{' '}
            {new Date(election.filing_deadline + 'T00:00:00').toLocaleDateString(
              'en-US',
              { month: 'long', day: 'numeric', year: 'numeric' },
            )}
          </p>
        )}
      </header>

      {/* Summary narrative */}
      {fundraising.length > 0 && (
        <section className="bg-white border border-slate-200 rounded-lg p-5 mb-8">
          <h2 className="text-lg font-semibold text-civic-navy mb-3">
            Campaign Finance Overview
          </h2>
          <p className="text-sm text-slate-600 leading-relaxed">
            {fundraising.length} candidate{fundraising.length !== 1 ? 's' : ''}{' '}
            linked to this election have received a combined{' '}
            <span className="font-medium">
              ${totalRaised.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
            </span>{' '}
            across{' '}
            <span className="font-medium">
              {totalContributions.toLocaleString()}
            </span>{' '}
            contributions from campaign finance filings.
          </p>
        </section>
      )}

      {/* Candidates grouped by office */}
      {fundraising.length === 0 && (
        <p className="text-slate-500 italic mb-8">
          No candidates have been linked to this election yet. Candidate records
          are derived from campaign committee filings.
        </p>
      )}

      {Array.from(byOffice.entries()).map(([office, candidates]) => (
        <section key={office} className="mb-8">
          <h2 className="text-lg font-semibold text-civic-navy mb-4">
            {office}
          </h2>
          <div className="space-y-4">
            {candidates.map((candidate) => (
              <CandidateCard key={candidate.candidate_name} candidate={candidate} />
            ))}
          </div>
        </section>
      ))}

      {election.notes && (
        <section className="mt-8 pt-6 border-t border-slate-200">
          <p className="text-xs text-slate-500">{election.notes}</p>
        </section>
      )}

      <footer className="mt-8 pt-6 border-t border-slate-200">
        <p className="text-xs text-slate-400">
          Candidate and fundraising data is derived from NetFile and CAL-ACCESS
          campaign finance filings. Committee-to-candidate matching is automated
          and may contain errors. Contribution totals include all filings linked
          to the candidate&apos;s primary campaign committee.
        </p>
        {election.source_url && (
          <p className="text-xs text-slate-400 mt-2">
            Election date source:{' '}
            <a
              href={election.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-civic-navy hover:underline"
            >
              California Secretary of State
            </a>
          </p>
        )}
      </footer>
    </div>
  )
}

function CandidateCard({ candidate }: { candidate: CandidateFundraising }) {
  const hasFinanceData = candidate.contribution_count > 0

  return (
    <div className="bg-white border border-slate-200 rounded-lg p-5">
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="text-base font-semibold text-civic-navy">
            {candidate.candidate_name}
          </h3>
          <div className="flex items-center gap-2 mt-1">
            {candidate.is_incumbent && (
              <span className="inline-block px-2 py-0.5 text-xs font-medium bg-civic-navy/10 text-civic-navy rounded">
                Incumbent
              </span>
            )}
            <span
              className={`inline-block px-2 py-0.5 text-xs font-medium rounded ${
                candidate.status === 'elected'
                  ? 'bg-green-50 text-green-700'
                  : candidate.status === 'defeated'
                    ? 'bg-red-50 text-red-600'
                    : candidate.status === 'withdrawn'
                      ? 'bg-slate-100 text-slate-500'
                      : 'bg-slate-50 text-slate-600'
              }`}
            >
              {candidate.status}
            </span>
          </div>
        </div>
      </div>

      {hasFinanceData ? (
        <div className="text-sm text-slate-600 leading-relaxed">
          <p>
            {candidate.candidate_name} has raised{' '}
            <span className="font-medium text-civic-navy">
              ${candidate.total_raised.toLocaleString('en-US', {
                minimumFractionDigits: 0,
                maximumFractionDigits: 0,
              })}
            </span>{' '}
            from{' '}
            <span className="font-medium">{candidate.donor_count.toLocaleString()}</span>{' '}
            donors across{' '}
            <span className="font-medium">
              {candidate.contribution_count.toLocaleString()}
            </span>{' '}
            contributions.
          </p>
          <p className="text-xs text-slate-500 mt-2">
            Average contribution: $
            {candidate.avg_contribution.toLocaleString('en-US', {
              minimumFractionDigits: 0,
              maximumFractionDigits: 0,
            })}
            {' · '}
            Largest: $
            {candidate.largest_contribution.toLocaleString('en-US', {
              minimumFractionDigits: 0,
              maximumFractionDigits: 0,
            })}
          </p>
        </div>
      ) : (
        <p className="text-sm text-slate-400 italic">
          No campaign finance data linked to this candidate yet.
        </p>
      )}
    </div>
  )
}
