import Link from 'next/link'
import { notFound } from 'next/navigation'
import type { Metadata } from 'next'
import {
  getElectionBySlug,
  getElectionWithCandidates,
  getCandidateFundingBreakdown,
  getCandidateIESupport,
} from '@/lib/queries'
import type {
  CandidateFundingBreakdown,
  CandidateIESupporter,
  ElectionCandidate,
} from '@/lib/types'
import CandidateFundingPanel from '@/components/CandidateFundingPanel'
import OperatorGate from '@/components/OperatorGate'
import { requireOperatorPage } from '@/lib/operator-page'

interface PageProps {
  params: Promise<{ slug: string }>
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  await requireOperatorPage()

  const { slug } = await params
  const election = await getElectionBySlug(slug)
  const title = election
    ? `Mayor's Race Funding | ${election.election_name} | Richmond Commons`
    : "Mayor's Race Funding | Richmond Commons"
  return {
    title,
    description: 'Where each Mayor candidate gets their campaign money, updated as new filings post.',
    robots: { index: false, follow: false },
  }
}

/** Last name extractor for IE name matching. Uses last whitespace-separated
 *  token; works for all three 2026 Mayor candidates (Anderson, Jimenez,
 *  Martinez). Operator should vet for compound surnames before adding new
 *  races. */
function lastNameOf(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).filter(Boolean)
  return parts[parts.length - 1] ?? fullName
}

interface PanelData {
  candidate: ElectionCandidate
  breakdown: CandidateFundingBreakdown | null
  ieSupporters: CandidateIESupporter[]
}

export default async function MayorFundingPage({ params }: PageProps) {
  await requireOperatorPage()

  const { slug } = await params
  const election = await getElectionBySlug(slug)
  if (!election) notFound()

  const electionDetail = await getElectionWithCandidates(election.id)
  if (!electionDetail) notFound()

  const mayorCandidates = electionDetail.candidates.filter(
    (c) => c.office_sought?.toLowerCase() === 'mayor',
  )

  if (mayorCandidates.length === 0) {
    return (
      <OperatorGate>
        <main className="max-w-3xl mx-auto px-4 sm:px-6 py-8">
          <h1 className="text-2xl font-bold text-civic-navy">Mayor&apos;s Race Funding</h1>
          <p className="mt-3 text-sm text-civic-slate">
            No Mayor candidates found for {election.election_name}.
          </p>
        </main>
      </OperatorGate>
    )
  }

  // Fetch breakdown + IE support for every candidate in parallel
  const panels: PanelData[] = await Promise.all(
    mayorCandidates.map(async (candidate) => {
      const [breakdown, ieSupporters] = await Promise.all([
        candidate.committee_id
          ? getCandidateFundingBreakdown(candidate.committee_id)
          : Promise.resolve(null),
        getCandidateIESupport(lastNameOf(candidate.candidate_name)),
      ])
      return { candidate, breakdown, ieSupporters }
    }),
  )

  // Sort: highest total raised (own committee) first, then alphabetical
  panels.sort((a, b) => {
    const aTotal = a.breakdown?.total_raised ?? 0
    const bTotal = b.breakdown?.total_raised ?? 0
    if (bTotal !== aTotal) return bTotal - aTotal
    return a.candidate.candidate_name.localeCompare(b.candidate.candidate_name)
  })

  const electionDate = new Date(election.election_date + 'T00:00:00')
  const electionDateFormatted = electionDate.toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  })

  return (
    <OperatorGate>
      <main className="max-w-3xl mx-auto px-4 sm:px-6 py-8">
        <Link
          href={`/elections/${slug}`}
          className="inline-flex items-center gap-1 text-sm text-civic-navy/60 hover:text-civic-navy transition-colors"
        >
          <span aria-hidden="true">&larr;</span>
          {election.election_name}
        </Link>

        <header className="mt-5 mb-6">
          <h1 className="text-2xl font-bold text-civic-navy">Where the money comes from</h1>
          <p className="mt-2 text-sm text-civic-slate">
            Mayor candidates in the {election.election_name} (election day {electionDateFormatted}),
            sorted by total raised. Each panel breaks down direct campaign contributions by source,
            then lists separate independent expenditure committees spending on each candidate&apos;s behalf.
          </p>
          <p className="mt-2 text-xs text-civic-slate/70">
            Operator-only. Numbers refresh every hour from NetFile filings via the Richmond City Clerk.
          </p>
        </header>

        <div className="space-y-5">
          {panels.map((p) => (
            <CandidateFundingPanel
              key={p.candidate.id}
              candidateName={p.candidate.candidate_name}
              officeSought={p.candidate.office_sought ?? 'Mayor'}
              breakdown={p.breakdown}
              ieSupporters={p.ieSupporters}
            />
          ))}
        </div>

        <section className="mt-8 rounded-lg border border-slate-200 bg-slate-50 p-4 text-xs text-civic-slate/80">
          <p className="font-semibold text-civic-slate">A note on the classifications</p>
          <p className="mt-1">
            Contributor types (individual, labor union, for-profit company, other political committee)
            are set when contributions are loaded from filings, using a combination of the FPPC entity
            code and donor-name pattern matching. The classifier is conservative on union-name patterns
            and flags ambiguous entities for operator review. Independent expenditure committees are
            matched to each candidate by committee name (&ldquo;supporting [name]&rdquo;) and by the
            candidate-name field in filed expenditures.
          </p>
        </section>
      </main>
    </OperatorGate>
  )
}
