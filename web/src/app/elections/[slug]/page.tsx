import Link from 'next/link'
import type { Metadata } from 'next'
import NovemberElection from '@/components/NovemberElection'
import {
  getElectionBySlug,
  getElectionWithCandidates,
} from '@/lib/queries'
import RaceSection from '@/components/RaceSection'
import type { CandidateFinanceCoverageById } from '@/components/CandidateCard'
import { ANDERSON_MONEY_PATH } from '@/lib/anderson-finance'
import type { ElectionCandidate } from '@/lib/types'
import { JIMENEZ_FINANCE, JIMENEZ_MONEY_PATH } from '@/lib/jimenez-finance'
import { S29_PUBLIC_TREATMENT_ENABLED } from '@/lib/s29-release-phase'
import {
  canonicalUrl,
  electionPageStructuredData,
  serializeJsonLd,
} from '@/lib/structured-data'


interface PageProps {
  params: Promise<{ slug: string }>
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params
  if (slug === '2026-general') return {
    title: 'Richmond November 2026: Mayor, Fire-Station Bond & Campaign Money',
    description: 'Richmond, California’s November 3 municipal guide: the mayoral runoff, proposed fire-station bond, source-linked campaign reports, and voting dates.',
    alternates: { canonical: canonicalUrl('/elections/2026-general') },
  }
  const election = await getElectionBySlug(slug)
  if (!election) {
    return {
      title: S29_PUBLIC_TREATMENT_ENABLED
        ? 'Election Not Found'
        : 'Election Not Found | Richmond Commons',
    }
  }

  if (!S29_PUBLIC_TREATMENT_ENABLED) {
    // Preserve the production metadata throughout the measured baseline.
    const candidates = await getElectionWithCandidates(election.id)
    const candidateNames = candidates?.candidates
      ?.map((candidate) => candidate.candidate_name)
      .slice(0, 6)
      .join(', ') ?? ''
    const candidateSnippet = candidateNames
      ? ` Candidates: ${candidateNames}.`
      : ''
    const races = slug === '2026-primary'
      ? ' Races: Mayor, District 2, District 3, District 4.'
      : ''

    return {
      title: `${election.election_name}: Candidates & Campaign Finance | Richmond Commons`,
      description: `Richmond ${election.election_name}: candidate records and voter information.${races}${candidateSnippet}`,
      openGraph: {
        title: `${election.election_name} | Richmond Commons`,
        description: `Find candidate records and voter information for the ${election.election_name}.`,
      },
    }
  }

  const year = election.election_date.slice(0, 4)
  const electionName = election.election_name
    ?? `${year} ${election.election_type} election`
  const description = `${electionName} information for Richmond, California, including candidates, voter information, and public campaign-finance filings when available.`
  const url = canonicalUrl(`/elections/${encodeURIComponent(slug)}`)
  return {
    title: `${electionName}: Candidates & Campaign Finance`,
    description,
    alternates: { canonical: url },
    openGraph: {
      title: `${electionName} | Richmond Commons`,
      description,
      url,
    },
  }
}

export default async function ElectionPage({ params }: PageProps) {
  if ((await params).slug === '2026-general') return <NovemberElection />
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
        <Link href="/" className="text-civic-navy hover:underline text-sm">
          &larr; Home
        </Link>
      </div>
    )
  }

  const electionDetail = await getElectionWithCandidates(election.id)
  const candidates = electionDetail?.candidates ?? []

  const electionName = election.election_name
    ?? `${election.election_date.slice(0, 4)} ${election.election_type} election`
  const pageDescription = `${electionName} information for Richmond, California, including candidates, voter information, and public campaign-finance filings when available.`
  const date = new Date(election.election_date + 'T00:00:00')
  const formattedDate = date.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
  const isUpcoming = date >= new Date()
  // Group candidates by office
  const byOffice = new Map<string, ElectionCandidate[]>()
  for (const c of candidates) {
    const existing = byOffice.get(c.office_sought) || []
    existing.push(c)
    byOffice.set(c.office_sought, existing)
  }

  const sortedOffices = Array.from(byOffice.entries()).sort(([a], [b]) => {
    if (a === 'Mayor') return -1
    if (b === 'Mayor') return 1
    return a.localeCompare(b)
  })

  // Exact verified spellings in the primary roster and the source-checked
  // committee reports. Do not treat the Jan-Jun summary as primary-only money.
  const financeCoverage: CandidateFinanceCoverageById = slug === '2026-primary'
    ? Object.fromEntries(candidates
      .filter(candidate => candidate.office_sought === 'Mayor'
        && (['Ahmad J. Anderson', 'Ahmad Anderson'].includes(candidate.candidate_name)
          || candidate.official_id === JIMENEZ_FINANCE.identity.official_id))
      .map(candidate => [candidate.id, {
        kind: 'source-checked-summary' as const,
        href: candidate.official_id === JIMENEZ_FINANCE.identity.official_id ? JIMENEZ_MONEY_PATH : ANDERSON_MONEY_PATH,
        scopeNote: 'The dated summary includes reports after this primary. Its figures are not primary-only totals.',
      }]))
    : {}

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {S29_PUBLIC_TREATMENT_ENABLED && (
        <script
          id="election-structured-data"
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: serializeJsonLd(electionPageStructuredData({
              name: electionName,
              electionDate: election.election_date,
              slug,
              description: pageDescription,
              sourceUrl: election.source_url,
            })),
          }}
        />
      )}

      <header className="mb-10">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-civic-navy">
              {electionName}
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

      </header>

      {slug === '2026-primary' && <p className="mb-6 rounded-lg border border-slate-200 p-4 leading-relaxed text-slate-700">This is the June candidate roster. <Link href="/elections/2026-general" className="text-civic-navy underline">Open the November guide</Link> for the mayoral runoff, current campaign reports and voting information.</p>}
      {sortedOffices.map(([office, officeCandidates]) => <RaceSection key={office}
        office={office} candidates={officeCandidates} id={officeToHashId(office)} electionSlug={slug} financeCoverage={financeCoverage} />)}
      {candidates.length === 0 && <p className="mb-8 text-slate-600">No candidate roster has been published here for this election. See the official election source below.</p>}

      {/* Source attribution */}
      <footer className="mt-10 pt-6 border-t border-slate-200 space-y-2">
        <p className="text-sm leading-relaxed text-slate-600">Candidates are listed alphabetically within each office. Having one name in our records does not establish that a race was unopposed. Campaign reports cover their stated dates; a report filed after an election is not a total for that election.</p>
        <p className="text-sm text-slate-600"><a href={election.source_url || 'https://www.contracostavote.gov/'} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center text-civic-navy underline">Official election information</a></p>
        <Link href="/elections/methodology" className="inline-flex min-h-11 items-center text-sm text-civic-navy underline">How we show campaign money</Link>
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
