import { notFound } from 'next/navigation'
import Link from 'next/link'
import type { Metadata } from 'next'


import {
  getOfficialBySlug,
  getOfficialVotingRecord,
  getOfficialContributions,
} from '@/lib/queries'
import DonorTable from '@/components/DonorTable'
import VotingRecordTable from '@/components/VotingRecordTable'
import BioSummary from '@/components/BioSummary'
import OperatorGate from '@/components/OperatorGate'
import OperatorCouncilSections from '@/components/OperatorCouncilSections'
import SuggestCorrectionLink from '@/components/SuggestCorrectionLink'
import JimenezFinanceSummary from '@/components/JimenezFinanceSummary'
import { JIMENEZ_FINANCE } from '@/lib/jimenez-finance'
import { getJimenezFilingCoverage } from '@/lib/queries/candidate-filing-coverage'
import { S29_PUBLIC_TREATMENT_ENABLED } from '@/lib/s29-release-phase'
import {
  canonicalUrl,
  councilProfileStructuredData,
  serializeJsonLd,
} from '@/lib/structured-data'

export const dynamic = 'force-static'
export const revalidate = 86400

function formatRole(role: string): string {
  return role.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '\u2014'
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
}

export async function generateMetadata(
  { params }: { params: Promise<{ slug: string }> }
): Promise<Metadata> {
  const { slug } = await params
  const official = await getOfficialBySlug(slug)
  if (!official) return { title: 'Official Not Found' }
  const title = `${official.name}, ${formatRole(official.role)}`
  const description = `Recorded council votes and campaign finance sources for ${official.name}, Richmond City Council.`
  const url = canonicalUrl(`/council/${encodeURIComponent(slug)}`)
  return {
    title,
    description,
    ...(S29_PUBLIC_TREATMENT_ENABLED
      ? { alternates: { canonical: url } }
      : {}),
    openGraph: {
      title: `${title} | Richmond Commons`,
      description,
      type: 'profile',
      ...(S29_PUBLIC_TREATMENT_ENABLED ? { url } : {}),
    },
  }
}

export default async function CouncilMemberPage({
  params,
}: {
  params: Promise<{ slug: string }>
}) {
  const { slug } = await params
  const official = await getOfficialBySlug(slug)
  if (!official) notFound()
  const hasJimenezMayoralCampaign = official.id === JIMENEZ_FINANCE.identity.official_id

  // Keep read failures uncaught. Next ISR retains the last successful page
  // when revalidation throws; a first render fails honestly instead of
  // caching a temporary fallback for this route's full 24-hour lifetime.
  const votingRecordPromise = getOfficialVotingRecord(official.id)

  const [votingRecord, contributions, jimenezCoverage] = await Promise.all([
    votingRecordPromise,
    getOfficialContributions(official.id),
    hasJimenezMayoralCampaign ? getJimenezFilingCoverage() : Promise.resolve(null),
  ])

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {S29_PUBLIC_TREATMENT_ENABLED && (
        <script
          id="council-profile-structured-data"
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: serializeJsonLd(councilProfileStructuredData({
              name: official.name,
              role: official.role,
              seat: official.seat,
              slug,
              isCurrent: official.is_current,
            })),
          }}
        />
      )}
      {/* ── Layer 1: Identity & Role Context (T6) ────────────────── */}
      <div className="mb-6">
        <Link href="/council" className="text-sm text-civic-navy-light hover:text-civic-navy">
          &larr; All Council Members
        </Link>
        <h1 className="text-3xl font-bold text-civic-navy mt-2">{official.name}</h1>
        <div className="flex flex-wrap gap-4 mt-2 text-sm text-slate-600">
          <span className="capitalize">{formatRole(official.role)}</span>
          {official.seat && official.seat.toLowerCase() !== official.role.toLowerCase() && (
            <span className="font-medium">{official.seat}</span>
          )}
          {official.term_start && (
            <span>
              Term: {formatDate(official.term_start)}
              {official.term_end ? ` \u2013 ${formatDate(official.term_end)}` : ' \u2013 present'}
            </span>
          )}
          {!official.is_current && (
            <span className="text-xs bg-slate-100 text-slate-500 px-2 py-0.5 rounded">Former</span>
          )}
        </div>

      </div>

      {/* Section jump nav */}
      <nav className="flex gap-4 text-sm text-slate-400 mb-6 border-b border-slate-100 pb-3">
        <a href="#summary" className="hover:text-civic-navy transition-colors">Summary</a>
        <a href="#contributions" className="hover:text-civic-navy transition-colors">Contributions</a>
        <a href="#votes" className="hover:text-civic-navy transition-colors">Votes</a>
      </nav>

      {/* Summary — auto-generated voting record narrative */}
      <div id="summary" className="scroll-mt-20" />
      <BioSummary
        officialName={official.name}
        votes={votingRecord}
      />

      {/* ── Layer 2: Activity Data (T6) ──────────────────────────── */}

      {/* Campaign Contributions — public. Tier 1 NetFile/FPPC donor records,
          same factual data shape already published on candidate pages and
          financial-connections. Graduated 2026-05-31. */}
      <section id="contributions" className="mb-8 scroll-mt-20">
        <h2 className="text-xl font-semibold text-slate-800 mb-3">
          Campaign money
        </h2>
        {hasJimenezMayoralCampaign && <div className="mb-8 rounded-lg border border-slate-200 p-5">
          <h3 className="text-lg font-semibold text-civic-navy">2026 campaign for mayor</h3>
          <JimenezFinanceSummary coverage={jimenezCoverage ?? undefined} />
        </div>}
        <h3 className="text-lg font-semibold text-civic-navy mb-2">{hasJimenezMayoralCampaign ? 'Council campaign records' : 'Campaign records'}</h3>
        {hasJimenezMayoralCampaign && <p className="text-slate-600 mb-4">
          Her mayoral campaign uses a separate committee and is covered above.
        </p>}
        <DonorTable contributions={contributions} />
      </section>

      {/* Voting Record — activity data (T6) */}
      <section id="votes" className="mb-8 scroll-mt-20">
        <div className="flex items-baseline justify-between gap-4 mb-3 flex-wrap">
          <h2 className="text-xl font-semibold text-slate-800">
            Voting Record
          </h2>
          <Link
            href="/council/analytics"
            className="text-sm text-civic-navy-light hover:text-civic-navy"
          >
            See recorded split votes across the council &rarr;
          </Link>
        </div>
        <VotingRecordTable votes={votingRecord} />
      </section>

      {/* ── Layer 3: Flagged Findings (T6) ───────────────────────── */}
      {/* Separated from activity data to avoid accusatory framing */}

      {/* Financial Disclosures (Form 700) — S28.1, Graduated tier.
          Operator-gated pending validation of the first real council data
          (registry: council-economic-interests-section). The jump-nav anchor
          for #disclosures is added at graduation, not before. */}
      <OperatorGate>
        <OperatorCouncilSections officialId={official.id} officialName={official.name} />
      </OperatorGate>

      {/* Correction link — at bottom, not competing with header */}
      <div className="mt-8 pt-6 border-t border-slate-100">
        <SuggestCorrectionLink />
      </div>
    </div>
  )
}
