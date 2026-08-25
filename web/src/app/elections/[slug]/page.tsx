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
      description: `Richmond ${election.election_name}: candidates, campaign fundraising, top donors, and voter information.${races}${candidateSnippet}`,
      openGraph: {
        title: `${election.election_name} | Richmond Commons`,
        description: `Track candidates, fundraising, and voter information for the ${election.election_name}.`,
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

  const [electionDetail, fundraising] = await Promise.all([
    getElectionWithCandidates(election.id),
    getCandidateFundraisingDetails(election.id, undefined, election.election_date),
  ])

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

  // Guard: general elections only show candidate data after the preceding
  // primary has been certified and its candidates populated. If a general
  // election has no linked candidates it means either (a) primary results
  // haven't been certified yet or (b) the general candidate rows haven't
  // been seeded yet. In either case, show a plain-language pending state
  // rather than an empty or garbled race list.
  //
  // How this recovers automatically: once a future migration seeds the
  // correct general-election candidates (with correct office_sought district
  // suffixes), ISR revalidation clears this banner and the full page renders.
  const isPendingGeneral =
    election.election_type === 'general' && fundraising.length === 0

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

        {/* Narrative lede. Graduated to public 2026-05-22 (D56b verification
            PR). Header narrative dollar amounts are sourced from Form 460
            cover totals via fundraising[].total_raised. */}
        {fundraising.length > 0 && (
          <p className="text-sm text-slate-600 leading-relaxed mt-4">
            {headerNarrative}
          </p>
        )}
      </header>

      {/* Pending state: general election before primary results are certified */}
      {isPendingGeneral ? (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-6 mb-8">
          <h2 className="text-base font-semibold text-slate-800 mb-2">
            Candidates will be listed after the primary is certified
          </h2>
          <p className="text-sm text-slate-600 leading-relaxed">
            The candidates for this election are determined by the June 2026 primary.
            Primary results are typically certified within a few weeks of election day.
            This page will update automatically once the candidate list is confirmed.
          </p>
          <p className="text-sm text-slate-500 mt-3">
            <Link href="/elections/2026-primary" className="text-civic-navy hover:underline">
              View the June 2026 primary results →
            </Link>
          </p>
        </div>
      ) : (
        <>
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
        </>
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
