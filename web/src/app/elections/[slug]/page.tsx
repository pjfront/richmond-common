import Link from 'next/link'
import type { Metadata } from 'next'
import {
  getElectionBySlug,
  getElectionWithCandidates,
  getCandidateFundraisingDetails,
} from '@/lib/queries'
import { buildElectionHeaderNarrative } from '@/lib/electionNarrative'
import RaceSection from '@/components/RaceSection'
import type { CandidateFundraisingDetail } from '@/lib/types'


interface PageProps {
  params: Promise<{ slug: string }>
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params
  const election = await getElectionBySlug(slug)
  if (!election) {
    return { title: 'Election Not Found — Richmond Commons' }
  }

  // Fetch candidates for richer SEO description
  const candidates = await getElectionWithCandidates(election.id)
  const candidateNames = candidates?.candidates
    ?.map((c) => c.candidate_name)
    .slice(0, 6)
    .join(', ') ?? ''
  const candidateSnippet = candidateNames ? ` Candidates: ${candidateNames}.` : ''

  const races = slug === '2026-primary'
    ? ' — Mayor, District 2, District 3, District 4'
    : ''
  return {
    title: `${election.election_name} — Candidates & Campaign Finance | Richmond Commons`,
    description: `Richmond ${election.election_name}: candidates, campaign fundraising, top donors, and voter information.${races}${candidateSnippet}`,
    openGraph: {
      title: `${election.election_name} — Richmond Commons`,
      description: `Track candidates, fundraising, and voter information for the ${election.election_name}.`,
    },
  }
}

export default async function ElectionPage({ params }: PageProps) {
  return <ElectionPageContent params={params} />
}

async function ElectionPageContent({ params }: PageProps) {
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
          &larr; All elections
        </Link>
      </div>
    )
  }

  const [electionDetail, fundraising] = await Promise.all([
    getElectionWithCandidates(election.id),
    getCandidateFundraisingDetails(election.id, undefined, election.election_date),
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

  // Voter registration deadline (15 days before election in CA for online reg)
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

  // Group candidates by office
  const byOffice = new Map<string, CandidateFundraisingDetail[]>()
  for (const c of fundraising) {
    const existing = byOffice.get(c.office_sought) || []
    existing.push(c)
    byOffice.set(c.office_sought, existing)
  }

  // Sort offices: Mayor first, then contested by district number, unopposed last
  const sortedOffices = Array.from(byOffice.entries()).sort(([a, aCands], [b, bCands]) => {
    if (a === 'Mayor') return -1
    if (b === 'Mayor') return 1
    const aUnopposed = aCands.length === 1
    const bUnopposed = bCands.length === 1
    if (aUnopposed !== bUnopposed) return aUnopposed ? 1 : -1
    return a.localeCompare(b)
  })

  const headerNarrative = buildElectionHeaderNarrative(byOffice)

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <Link
        href="/elections"
        className="text-sm text-civic-navy hover:underline mb-4 inline-block"
      >
        &larr; All elections
      </Link>

      <header className="mb-10">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-civic-navy">
              {election.election_name}
            </h1>
            <p className="text-slate-600 mt-1">{formattedDate}</p>
          </div>

          {isUpcoming && (
            <Link
              href="/elections/find-my-district"
              className="inline-flex items-center px-4 py-2 bg-civic-navy text-white rounded-md text-sm font-medium hover:bg-civic-navy-light transition-colors shrink-0"
            >
              Find your district
            </Link>
          )}
        </div>

        {isUpcoming && daysUntil > 0 && (
          <div className="mt-4 space-y-1">
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

        {/* Narrative lede replaces old stats box */}
        {fundraising.length > 0 && (
          <p className="text-sm text-slate-600 leading-relaxed mt-4">
            {headerNarrative}
          </p>
        )}
      </header>

      {/* Races — voter guide pattern */}
      {sortedOffices.map(([office, candidates]) => (
        <RaceSection
          key={office}
          office={office}
          candidates={candidates}
          isHeroRace={office === 'Mayor'}
          id={officeToHashId(office)}
          electionSlug={slug}
        />
      ))}

      {fundraising.length === 0 && electionDetail?.candidates && electionDetail.candidates.length > 0 && (
        <p className="text-slate-500 italic mb-8">
          Candidates have been identified but campaign finance data is still being linked.
        </p>
      )}

      {/* Source attribution */}
      <footer className="mt-10 pt-6 border-t border-slate-200 space-y-2">
        <p className="text-xs text-slate-400">
          Election dates from the California Secretary of State. Campaign finance
          data from{' '}
          <a
            href="https://public.netfile.com/pub2/?AID=RICH"
            target="_blank"
            rel="noopener noreferrer"
            className="text-civic-navy hover:underline"
          >
            NetFile
          </a>{' '}
          (City of Richmond e-filing system). Contribution totals reflect filings
          linked to each candidate&apos;s committee and may not include all
          fundraising activity.
        </p>
        <p className="text-xs text-slate-400">
          Auto-generated from public filings · Last updated hourly
        </p>
      </footer>
    </div>
  )
}

/** Convert office name to URL hash id: "Mayor" → "mayor", "City Council District 3" → "district-3" */
function officeToHashId(office: string): string {
  return office
    .toLowerCase()
    .replace(/^city council\s+/, '')
    .replace(/\s+/g, '-')
}
