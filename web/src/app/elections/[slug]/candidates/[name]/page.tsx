import { notFound } from 'next/navigation'
import Link from 'next/link'
import type { Metadata } from 'next'
import {
  getElectionBySlug,
  getCandidateFundraisingDetails,
  getOfficialWithStats,
  getOfficialCategoryBreakdown,
  getFullCandidateDonors,
  officialToSlug,
} from '@/lib/queries'
import type {
  CandidateFundraisingDetail,
  CandidateTopDonor,
  CandidateDonorsByCycle,
} from '@/lib/types'
import SuggestCorrectionLink from '@/components/SuggestCorrectionLink'
import OperatorGate from '@/components/OperatorGate'
import DonorSection from './DonorSection'

// ─── Types ──────────────────────────────────────────────────────

interface PageProps {
  params: Promise<{ slug: string; name: string }>
}

interface OfficialStats {
  vote_count: number
  attendance_rate: number
  meetings_attended: number
  meetings_total: number
  term_start: string | null
}

interface CategoryStat {
  category: string
  count: number
}

// ─── Metadata ───────────────────────────────────────────────────

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug, name } = await params
  const resolved = await resolveCandidate(slug, name)
  if (!resolved) return { title: 'Candidate Not Found — Richmond Commons' }

  const { candidate, election } = resolved
  const office = candidate.office_sought
  const electionName = election.election_name ?? 'Election'
  const title = `${candidate.candidate_name} — ${office} Candidate | Richmond ${electionName}`
  const description = buildLedeNarrative(candidate, [], election.election_date)

  return {
    title,
    description,
    openGraph: {
      title: `${candidate.candidate_name} — ${office} | Richmond Commons`,
      description,
      type: 'profile',
    },
  }
}

// ─── Page ───────────────────────────────────────────────────────

export default async function CandidateProfilePage({ params }: PageProps) {
  const { slug, name } = await params
  const resolved = await resolveCandidate(slug, name)
  if (!resolved) notFound()

  const { candidate, allCandidates, election } = resolved

  // Parallel fetches for incumbent data + full donors
  const [officialStats, categories, fullDonors] = await Promise.all([
    candidate.official_id ? getOfficialWithStats(candidate.official_id) : null,
    candidate.official_id ? getOfficialCategoryBreakdown(candidate.official_id) : [],
    candidate.committee_id
      ? getFullCandidateDonors(candidate.committee_id, election.election_date)
      : null,
  ])

  const electionDate = new Date(election.election_date + 'T00:00:00')
  const electionFormatted = electionDate.toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  })

  // Racemates: other candidates running for the same office
  const racemates = allCandidates.filter(
    (c) => c.office_sought === candidate.office_sought && c.candidate_name !== candidate.candidate_name,
  )

  const cycleYear = electionDate.getFullYear() - 1

  return (
    <OperatorGate>
      <article className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Breadcrumb */}
        <Link
          href={`/elections/${slug}`}
          className="text-sm text-civic-navy-light hover:text-civic-navy"
        >
          &larr; {election.election_name ?? '2026 Primary Election'}
        </Link>

        {/* Header */}
        <header className="mt-4 mb-8">
          <h1 className="text-3xl font-bold text-civic-navy">
            {candidate.candidate_name}
          </h1>
          <p className="text-slate-600 mt-1">
            Running for {candidate.office_sought}
            {candidate.is_incumbent && (
              <span className="ml-2 inline-block px-2 py-0.5 text-xs font-medium bg-civic-navy/10 text-civic-navy rounded">
                Incumbent
              </span>
            )}
          </p>
        </header>

        {/* ── Narrative ─────────────────────────────────────────── */}
        <div className="prose prose-slate max-w-none text-[15px] leading-relaxed space-y-4">
          {/* Paragraph 1: Identity + race context */}
          <p>{buildLedeNarrative(candidate, racemates, election.election_date)}</p>

          {/* Paragraph 2: Incumbent record (conditional) */}
          {officialStats && (categories as CategoryStat[]).length > 0 && (
            <p>
              {buildRecordNarrative(
                candidate.candidate_name,
                officialStats as OfficialStats,
                categories as CategoryStat[],
              )}
              {' '}
              <Link
                href={`/council/${officialToSlug(candidate.candidate_name)}`}
                className="text-civic-navy hover:underline no-underline"
              >
                View complete voting record &rarr;
              </Link>
            </p>
          )}

          {/* Paragraph 3: Follow the money */}
          <p>
            {buildMoneyNarrative(candidate, cycleYear)}
          </p>

          {/* Prior activity context (conditional) */}
          {candidate.lifetime_raised > candidate.total_raised && candidate.earliest_contribution && (
            <p className="text-sm text-slate-500">
              {buildPriorActivityNarrative(candidate, cycleYear)}
            </p>
          )}
        </div>

        {/* ── Expandable detail sections ────────────────────────── */}
        <div className="mt-10 space-y-4">
          {/* Full donor list */}
          {fullDonors && (fullDonors.cycleDonors.length > 0 || fullDonors.priorDonors.length > 0) && (
            <DonorSection donors={fullDonors} />
          )}

          {/* Incumbent: link to full voting record */}
          {candidate.is_incumbent && candidate.official_id && (
            <div className="border border-slate-200 rounded-lg p-4">
              <Link
                href={`/council/${officialToSlug(candidate.candidate_name)}`}
                className="text-sm font-medium text-civic-navy hover:underline"
              >
                View complete voting record on council profile &rarr;
              </Link>
              {officialStats && (
                <p className="text-xs text-slate-500 mt-1">
                  {(officialStats as OfficialStats).vote_count.toLocaleString()} votes across{' '}
                  {(officialStats as OfficialStats).meetings_total} meetings
                </p>
              )}
            </div>
          )}
        </div>

        {/* ── Also in this race ─────────────────────────────────── */}
        {racemates.length > 0 && (
          <section className="mt-10 pt-6 border-t border-slate-200">
            <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">
              Also running for {candidate.office_sought}
            </h2>
            <ul className="space-y-2">
              {racemates.map((r) => (
                <li key={r.candidate_name} className="flex items-center justify-between text-sm">
                  <Link
                    href={`/elections/${slug}/candidates/${candidateToSlug(r.candidate_name)}`}
                    className="text-civic-navy hover:underline font-medium"
                  >
                    {r.candidate_name}
                    {r.is_incumbent && (
                      <span className="ml-1.5 text-[10px] font-medium text-civic-navy/60">
                        incumbent
                      </span>
                    )}
                  </Link>
                  <span className="text-slate-400 tabular-nums text-xs">
                    {r.total_raised > 0
                      ? `$${fmtNum(r.total_raised)} · ${r.donor_count} donor${r.donor_count !== 1 ? 's' : ''}`
                      : 'No filings linked'}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* ── Source footer ──────────────────────────────────────── */}
        <footer className="mt-10 pt-6 border-t border-slate-200 space-y-3">
          <p className="text-xs text-slate-400">
            Campaign finance data from{' '}
            <a
              href="https://public.netfile.com/pub2/?AID=RICH"
              target="_blank"
              rel="noopener noreferrer"
              className="text-civic-navy hover:underline"
            >
              NetFile
            </a>{' '}
            (City of Richmond e-filing system, Tier 1 source). Election dates from
            the California Secretary of State. Fundraising totals for this election
            cover contributions since January {cycleYear}.
          </p>
          <p className="text-xs text-slate-400">
            Auto-generated from public records &middot; Updated hourly
          </p>
          <SuggestCorrectionLink />
        </footer>
      </article>
    </OperatorGate>
  )
}

// ─── Data resolution ────────────────────────────────────────────

async function resolveCandidate(electionSlug: string, nameSlug: string) {
  const election = await getElectionBySlug(electionSlug)
  if (!election) return null

  const allCandidates = await getCandidateFundraisingDetails(
    election.id,
    undefined,
    election.election_date,
  )
  if (!allCandidates.length) return null

  const candidate = allCandidates.find(
    (c) => candidateToSlug(c.candidate_name) === nameSlug,
  )
  if (!candidate) return null

  return { candidate, allCandidates, election }
}

function candidateToSlug(name: string): string {
  return name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '')
}

// ─── Narrative builders ─────────────────────────────────────────

function buildLedeNarrative(
  candidate: CandidateFundraisingDetail,
  racemates: CandidateFundraisingDetail[],
  electionDate: string,
): string {
  const date = new Date(electionDate + 'T00:00:00')
  const dateStr = date.toLocaleDateString('en-US', { month: 'long', day: 'numeric' })

  const parts: string[] = []

  if (candidate.is_incumbent) {
    parts.push(
      `${candidate.candidate_name} is the incumbent ${candidate.office_sought}.`,
    )
  } else {
    parts.push(
      `${candidate.candidate_name} is running for ${candidate.office_sought} in the June ${dateStr.split(' ')[1]} primary.`,
    )
  }

  if (racemates.length > 0) {
    const verb = candidate.is_incumbent ? 'faces' : 'is one of'
    const count = racemates.length + 1
    if (candidate.is_incumbent) {
      parts.push(
        `${candidate.candidate_name.split(' ')[0]} ${verb} ${racemates.length} challenger${racemates.length !== 1 ? 's' : ''} in the June ${dateStr.split(' ')[1]} primary.`,
      )
    } else {
      parts.push(`${count} candidates are running for this seat.`)
    }
  }

  return parts.join(' ')
}

function buildRecordNarrative(
  name: string,
  stats: OfficialStats,
  categories: CategoryStat[],
): string {
  const firstName = name.split(' ')[0]
  const topCategories = categories.slice(0, 3).map((c) => c.category.toLowerCase())
  const attendancePct = Math.round(stats.attendance_rate * 100)

  const parts: string[] = []

  parts.push(
    `During ${firstName}'s time in office, the council has voted on ${stats.vote_count.toLocaleString()} items across ${stats.meetings_total} meetings.`,
  )

  if (topCategories.length > 0) {
    const categoryList =
      topCategories.length === 1
        ? topCategories[0]
        : topCategories.length === 2
          ? `${topCategories[0]} and ${topCategories[1]}`
          : `${topCategories[0]}, ${topCategories[1]}, and ${topCategories[2]}`
    parts.push(
      `Votes have focused primarily on ${categoryList}.`,
    )
  }

  if (stats.meetings_total > 0) {
    parts.push(`${firstName} has attended ${attendancePct}% of meetings.`)
  }

  return parts.join(' ')
}

function buildMoneyNarrative(
  candidate: CandidateFundraisingDetail,
  cycleYear: number,
): string {
  if (candidate.total_raised === 0 && candidate.lifetime_raised === 0) {
    return 'No campaign finance filings have been linked to this candidate.'
  }

  if (candidate.total_raised === 0) {
    return `No fundraising has been recorded for this election cycle (since January ${cycleYear}).`
  }

  const parts: string[] = []

  parts.push(
    `For this election, ${candidate.candidate_name.split(' ')[0]}'s committee has raised $${fmtNum(candidate.total_raised)} from ${candidate.donor_count} donor${candidate.donor_count !== 1 ? 's' : ''} since January ${cycleYear}.`,
  )

  // Typical contribution
  if (candidate.avg_contribution > 0) {
    parts.push(
      `The typical contribution is $${fmtNum(candidate.avg_contribution)}.`,
    )
  }

  // Top donors (name up to 2)
  if (candidate.top_donors.length > 0) {
    const topNames = candidate.top_donors
      .slice(0, 2)
      .map((d) => d.donor_name)
    if (topNames.length === 1) {
      parts.push(`The largest supporter is ${topNames[0]}.`)
    } else {
      parts.push(
        `The largest supporters include ${topNames[0]} and ${topNames[1]}.`,
      )
    }
  }

  // Contribution composition
  const { small, medium, large, major, total_count } = candidate.contribution_breakdown
  if (total_count > 0) {
    const majorPct = Math.round((major / total_count) * 100)
    const smallPct = Math.round((small / total_count) * 100)
    if (majorPct > 50) {
      parts.push(
        `Most fundraising comes from contributions of $1,000 or more (${majorPct}% of contributions).`,
      )
    } else if (smallPct > 50) {
      parts.push(
        `Most contributions are under $100 (${smallPct}% of all contributions).`,
      )
    }
  }

  return parts.join(' ')
}

function buildPriorActivityNarrative(
  candidate: CandidateFundraisingDetail,
  cycleYear: number,
): string {
  const priorAmount = candidate.lifetime_raised - candidate.total_raised
  if (priorAmount <= 0) return ''

  const earliest = candidate.earliest_contribution
    ? new Date(candidate.earliest_contribution + 'T00:00:00').toLocaleDateString('en-US', {
        month: 'short',
        year: 'numeric',
      })
    : null

  if (earliest) {
    return `The committee previously raised $${fmtNum(priorAmount)} between ${earliest} and January ${cycleYear}, under prior election filings.`
  }
  return `The committee has raised $${fmtNum(candidate.lifetime_raised)} total across all election cycles.`
}

function fmtNum(n: number): string {
  return n.toLocaleString('en-US', { maximumFractionDigits: 0 })
}
