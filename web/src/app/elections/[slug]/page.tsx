import Link from 'next/link'
import type { Metadata } from 'next'
import {
  getElectionBySlug,
  getElectionWithCandidates,
  getElectionFundraisingSummary,
} from '@/lib/queries'
import SourceBadge from '@/components/SourceBadge'
import type { CandidateFundraising } from '@/lib/types'

export const dynamic = 'force-dynamic'
export const revalidate = 3600

interface PageProps {
  params: Promise<{ slug: string }>
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params
  const election = await getElectionBySlug(slug)
  if (!election) {
    return { title: 'Election Not Found — Richmond Commons' }
  }
  const races = slug === '2026-primary'
    ? ' — Mayor, District 2, District 3, District 4'
    : ''
  return {
    title: `${election.election_name} — Richmond Commons`,
    description: `Richmond ${election.election_name}: candidates, campaign fundraising, and voter information.${races}`,
    openGraph: {
      title: `${election.election_name} — Richmond Commons`,
      description: `Track candidates, fundraising, and voter information for the ${election.election_name}.`,
    },
  }
}

export default async function ElectionPage({ params }: PageProps) {
  const { slug } = await params
  const election = await getElectionBySlug(slug)

  if (!election) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold text-civic-navy mb-4">Election Not Found</h1>
        <p className="text-slate-600 mb-4">
          We couldn&apos;t find an election matching &ldquo;{slug}&rdquo;.
        </p>
        <Link href="/elections" className="text-civic-navy hover:underline text-sm">
          ← All elections
        </Link>
      </div>
    )
  }

  const [electionDetail, fundraising] = await Promise.all([
    getElectionWithCandidates(election.id),
    getElectionFundraisingSummary(election.id),
  ])

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

  // Voter registration deadline (21 days before election in CA)
  const regDeadline = new Date(date)
  regDeadline.setDate(regDeadline.getDate() - 15)
  const regFormatted = regDeadline.toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  })
  const daysUntilReg = Math.ceil(
    (regDeadline.getTime() - Date.now()) / (1000 * 60 * 60 * 24),
  )

  const totalRaised = fundraising.reduce((sum, c) => sum + c.total_raised, 0)

  // Group candidates by office
  const byOffice = new Map<string, CandidateFundraising[]>()
  for (const c of fundraising) {
    const existing = byOffice.get(c.office_sought) || []
    existing.push(c)
    byOffice.set(c.office_sought, existing)
  }

  // Sort offices: Mayor first, then by district number
  const sortedOffices = Array.from(byOffice.entries()).sort(([a], [b]) => {
    if (a === 'Mayor') return -1
    if (b === 'Mayor') return 1
    return a.localeCompare(b)
  })

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <Link
        href="/elections"
        className="text-sm text-civic-navy hover:underline mb-4 inline-block"
      >
        ← All elections
      </Link>

      <header className="mb-8">
        <h1 className="text-3xl font-bold text-civic-navy">
          {election.election_name}
        </h1>
        <p className="text-slate-600 mt-1">{formattedDate}</p>

        {isUpcoming && daysUntil > 0 && (
          <div className="mt-4 space-y-2">
            <p className="text-sm font-medium text-civic-amber">
              {daysUntil} days until election day
            </p>
            {daysUntilReg > 0 && (
              <p className="text-sm text-slate-600">
                Voter registration deadline: {regFormatted} ({daysUntilReg} days)
              </p>
            )}
          </div>
        )}
      </header>

      {/* Summary */}
      {totalRaised > 0 && (
        <section className="bg-white border border-slate-200 rounded-lg p-5 mb-8">
          <p className="text-sm text-slate-600 leading-relaxed">
            {fundraising.length} candidates are linked to this election.
            Those with campaign committees on file have raised a combined{' '}
            <span className="font-semibold text-civic-navy">
              ${totalRaised.toLocaleString('en-US', { maximumFractionDigits: 0 })}
            </span>{' '}
            in campaign contributions tracked through NetFile.
          </p>
        </section>
      )}

      {/* Races */}
      {sortedOffices.map(([office, candidates]) => (
        <RaceSection key={office} office={office} candidates={candidates} />
      ))}

      {fundraising.length === 0 && electionDetail?.candidates && electionDetail.candidates.length > 0 && (
        <p className="text-slate-500 italic mb-8">
          Candidates have been identified but campaign finance data is still being linked.
        </p>
      )}

      {/* Source attribution */}
      <footer className="mt-10 pt-6 border-t border-slate-200 space-y-3">
        <div className="flex items-center gap-2">
          <SourceBadge tier={1} source="CA Secretary of State" compact />
          <span className="text-xs text-slate-500">
            Election dates from the California Secretary of State.
          </span>
        </div>
        <div className="flex items-center gap-2">
          <SourceBadge tier={1} source="NetFile" compact />
          <span className="text-xs text-slate-500">
            Campaign finance data from{' '}
            <a
              href="https://public.netfile.com/pub2/?AID=RICH"
              target="_blank"
              rel="noopener noreferrer"
              className="text-civic-navy hover:underline"
            >
              NetFile
            </a>{' '}
            (City of Richmond e-filing system).
            Contribution totals reflect filings linked to each candidate&apos;s
            committee and may not include all fundraising activity.
          </span>
        </div>
        <p className="text-xs text-slate-400 mt-2">
          Auto-generated from public filings · Last updated hourly
        </p>
      </footer>
    </div>
  )
}

function RaceSection({
  office,
  candidates,
}: {
  office: string
  candidates: CandidateFundraising[]
}) {
  const contested = candidates.length > 1

  return (
    <section className="mb-8">
      <div className="flex items-center gap-3 mb-4">
        <h2 className="text-lg font-semibold text-civic-navy">{office}</h2>
        {!contested && (
          <span className="text-xs text-slate-400 italic">unopposed</span>
        )}
      </div>
      <div className="space-y-3">
        {candidates.map((candidate) => (
          <CandidateCard key={candidate.candidate_name} candidate={candidate} />
        ))}
      </div>
    </section>
  )
}

function CandidateCard({ candidate }: { candidate: CandidateFundraising }) {
  const hasFinanceData = candidate.contribution_count > 0

  return (
    <div className="bg-white border border-slate-200 rounded-lg p-5">
      <div className="flex items-start justify-between">
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
          </div>
        </div>
      </div>

      {hasFinanceData ? (
        <div className="mt-3 text-sm text-slate-600 leading-relaxed">
          <p>
            Raised{' '}
            <span className="font-medium text-civic-navy">
              ${candidate.total_raised.toLocaleString('en-US', {
                maximumFractionDigits: 0,
              })}
            </span>{' '}
            from{' '}
            <span className="font-medium">{candidate.donor_count.toLocaleString()}</span>{' '}
            donors.
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
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-400 italic">
          No campaign finance filings linked yet.
        </p>
      )}
    </div>
  )
}
