import { notFound } from 'next/navigation'
import Link from 'next/link'
import type { Metadata } from 'next'
import type { ReactNode } from 'react'
import {
  getElectionBySlug,
  getCandidateFundraisingDetails,
  getOfficialWithStats,
  getFullCandidateDonors,
  getMostCommentedVotes,
  computeAlignmentStats,
  officialToSlug,
} from '@/lib/queries'
import type { CandidateFundraisingDetail } from '@/lib/types'
import SuggestCorrectionLink from '@/components/SuggestCorrectionLink'
import OperatorGate from '@/components/OperatorGate'
import DonorSection from './DonorSection'
import VotedItemCard from './VotedItemCard'

// ─── Types ──────────────────────────────────────────────────────

interface PageProps {
  params: Promise<{ slug: string; name: string }>
}

interface BioFactual {
  majority_alignment_rate?: number
  sole_dissent_count?: number
  sole_dissent_categories?: Array<{ category: string; count: number }>
}

interface OfficialRecord {
  vote_count: number
  attendance_rate: number
  meetings_attended: number
  meetings_total: number
  term_start: string | null
  term_end: string | null
  is_current: boolean
  role: string
  seat: string | null
  bio_factual: BioFactual | null
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

  const cycleYear = new Date(election.election_date + 'T00:00:00').getFullYear() - 1
  let description = `${candidate.candidate_name} is ${candidate.is_incumbent ? `the incumbent ${office}` : `running for ${office}`} in the Richmond ${electionName}.`
  if (candidate.total_raised > 0) {
    description += ` Raised $${fmtNum(candidate.total_raised)} from ${candidate.donor_count} donors since January ${cycleYear}.`
  }

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

  const [officialRecord, fullDonors, commentedVotes] = await Promise.all([
    candidate.official_id ? getOfficialWithStats(candidate.official_id) : null,
    candidate.committee_id
      ? getFullCandidateDonors(candidate.committee_id, election.election_date)
      : null,
    candidate.official_id ? getMostCommentedVotes(candidate.official_id, 5) : [],
  ])

  const electionDate = new Date(election.election_date + 'T00:00:00')
  const cycleYear = electionDate.getFullYear() - 1

  const racemates = allCandidates.filter(
    (c) => c.office_sought === candidate.office_sought && c.candidate_name !== candidate.candidate_name,
  )

  const record = officialRecord as OfficialRecord | null

  // Backfill alignment stats if bio_factual is missing (former officials not yet regenerated)
  if (record && !record.bio_factual && candidate.official_id) {
    const computed = await computeAlignmentStats(candidate.official_id)
    record.bio_factual = {
      majority_alignment_rate: computed.majority_alignment_rate ?? undefined,
      sole_dissent_count: computed.sole_dissent_count,
    }
  }

  const hasRecord = record != null && record.vote_count > 0
  const initials = candidate.candidate_name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()

  return (
    <OperatorGate>
      <article className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Breadcrumb */}
        <Link
          href={`/elections/${slug}`}
          className="inline-flex items-center gap-1 text-sm text-civic-navy/60 hover:text-civic-navy transition-colors"
        >
          <span aria-hidden="true">&larr;</span>
          {election.election_name ?? '2026 Primary Election'}
        </Link>

        {/* ── Hero header ────────────────────────────────────────── */}
        <header className="mt-5 mb-8 flex items-start gap-5">
          {/* Initials avatar */}
          <div className="w-16 h-16 rounded-full bg-gradient-to-br from-civic-navy to-civic-navy-light text-white text-xl font-bold flex items-center justify-center shrink-0 mt-0.5">
            {initials}
          </div>
          <div className="min-w-0">
            <h1 className="text-3xl sm:text-4xl font-bold text-civic-navy tracking-tight">
              {candidate.candidate_name}
            </h1>
            <div className="flex flex-wrap items-center gap-2 mt-1.5">
              <span className="text-base text-slate-500">
                {candidate.office_sought}
              </span>
              <span className="text-slate-300" aria-hidden="true">&middot;</span>
              <span className="text-sm text-slate-400">
                June {electionDate.getDate()}, {electionDate.getFullYear()} Primary
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-2 mt-2">
              {candidate.is_incumbent && (
                <span className="px-2.5 py-0.5 text-[11px] font-semibold bg-civic-navy text-white rounded-full uppercase tracking-wide">
                  Incumbent
                </span>
              )}
              {hasRecord && !candidate.is_incumbent && record.is_current && (
                <span className="px-2.5 py-0.5 text-[11px] font-medium bg-slate-100 text-slate-600 rounded-full">
                  Current {formatRole(record.role)}
                </span>
              )}
              {hasRecord && !record.is_current && (
                <span className="px-2.5 py-0.5 text-[11px] font-medium bg-slate-100 text-slate-500 rounded-full">
                  Former {formatRole(record.role)}
                </span>
              )}
            </div>
          </div>
        </header>

        {/* ── Narrative card ─────────────────────────────────────── */}
        <div className="border-l-4 border-civic-navy bg-civic-navy/[0.02] rounded-r-lg p-5 sm:p-6 mb-6">
          <p className="text-[15px] text-slate-700 leading-[1.8]">
            {renderLedeNarrative(candidate, racemates, electionDate)}
          </p>
        </div>

        {/* ── Follow the money (first — the question voters ask) ─── */}
        <section className="mb-6">
          <div className="border-l-4 border-civic-amber/60 bg-civic-amber/[0.03] rounded-r-lg p-5 sm:p-6">
            <h2 className="text-xs font-semibold text-civic-amber uppercase tracking-widest mb-3">
              Follow the money
            </h2>
            <p className="text-[15px] text-slate-700 leading-[1.8]">
              {renderMoneyNarrative(candidate, cycleYear)}
            </p>

            {candidate.lifetime_raised > candidate.total_raised && candidate.earliest_contribution && (
              <p className="text-sm text-slate-500 mt-3">
                {renderPriorActivityNarrative(candidate, cycleYear)}
              </p>
            )}

            {fullDonors && (fullDonors.cycleDonors.length > 0 || fullDonors.priorDonors.length > 0) && (
              <div className="mt-4 pt-4 border-t border-civic-amber/10">
                <DonorSection donors={fullDonors} />
              </div>
            )}
          </div>
        </section>

        {/* ── Council record (conditional) ────────────────────────── */}
        {hasRecord && (
          <section className="mb-6">
            <div className="border border-slate-200 rounded-lg p-5 sm:p-6">
              <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-3">
                Council record
              </h2>
              <p className="text-[15px] text-slate-700 leading-[1.8]">
                {renderRecordNarrative(candidate, record)}
              </p>

              {/* Most-commented votes — meeting-page style cards */}
              {commentedVotes.length > 0 && (
                <div className="mt-5 pt-4 border-t border-slate-100">
                  <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-3">
                    Votes residents spoke up on
                  </h3>
                  <div className="space-y-3">
                    {commentedVotes.map((v) => (
                      <VotedItemCard
                        key={v.item_id}
                        vote={v}
                        candidateName={candidate.candidate_name}
                      />
                    ))}
                  </div>
                </div>
              )}

              <Link
                href={`/council/${officialToSlug(candidate.candidate_name)}`}
                className="inline-flex items-center gap-1 mt-4 text-sm font-medium text-civic-navy hover:underline"
              >
                View full voting record &rarr;
              </Link>
            </div>
          </section>
        )}

        {/* ── Also in this race ───────────────────────────────────── */}
        {racemates.length > 0 && (
          <section className="mt-10 pt-8 border-t border-slate-200">
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-4">
              Also running for {candidate.office_sought}
            </h2>
            <div className="grid gap-2">
              {racemates
                .sort((a, b) => b.total_raised - a.total_raised)
                .map((r) => {
                  const rInitials = r.candidate_name
                    .split(' ')
                    .map((n) => n[0])
                    .join('')
                    .slice(0, 2)
                  return (
                    <Link
                      key={r.candidate_name}
                      href={`/elections/${slug}/candidates/${candidateToSlug(r.candidate_name)}`}
                      className="flex items-center justify-between py-3 px-4 rounded-lg border border-slate-100 hover:border-civic-navy/20 hover:bg-slate-50/80 transition-all group"
                    >
                      <div className="flex items-center gap-3">
                        <span className="w-9 h-9 rounded-full bg-slate-100 text-slate-500 text-xs font-semibold flex items-center justify-center shrink-0 group-hover:bg-civic-navy/10 group-hover:text-civic-navy transition-colors">
                          {rInitials}
                        </span>
                        <div>
                          <span className="font-medium text-sm text-civic-navy group-hover:underline">
                            {r.candidate_name}
                          </span>
                          {r.is_incumbent && (
                            <span className="ml-2 px-1.5 py-0.5 text-[10px] font-semibold bg-civic-navy text-white rounded uppercase">
                              Incumbent
                            </span>
                          )}
                        </div>
                      </div>
                      <span className="text-xs text-slate-400 tabular-nums">
                        {r.total_raised > 0
                          ? `$${fmtNum(r.total_raised)} raised`
                          : 'No filings linked'}
                      </span>
                    </Link>
                  )
                })}
            </div>
          </section>
        )}

        {/* ── Source footer ────────────────────────────────────────── */}
        <footer className="mt-12 pt-6 border-t border-slate-100 space-y-2">
          <p className="text-xs text-slate-400 leading-relaxed">
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

function formatRole(role: string): string {
  return role.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

// ─── JSX narrative builders ─────────────────────────────────────

function renderLedeNarrative(
  candidate: CandidateFundraisingDetail,
  racemates: CandidateFundraisingDetail[],
  electionDate: Date,
): ReactNode {
  const dayNum = electionDate.getDate()
  const totalInRace = racemates.length + 1

  if (candidate.is_incumbent) {
    return (
      <>
        {candidate.candidate_name} is the <strong>incumbent {candidate.office_sought}</strong>,
        running for re-election in the June {dayNum} primary.
        {racemates.length > 0 && (
          <> {candidate.candidate_name.split(' ')[0]} faces{' '}
          <strong>{racemates.length} challenger{racemates.length !== 1 ? 's' : ''}</strong>.</>
        )}
      </>
    )
  }

  return (
    <>
      {candidate.candidate_name} is running for <strong>{candidate.office_sought}</strong> in
      the June {dayNum} primary.
      {racemates.length > 0 && (
        <> <strong>{totalInRace} candidates</strong> are running for this seat.</>
      )}
    </>
  )
}

function renderRecordNarrative(
  candidate: CandidateFundraisingDetail,
  record: OfficialRecord,
): ReactNode {
  const firstName = candidate.candidate_name.split(' ')[0]
  const roleName = formatRole(record.role).toLowerCase()
  const attendancePct = Math.round(record.attendance_rate * 100)
  const bio = record.bio_factual as BioFactual | null
  const alignmentPct = bio?.majority_alignment_rate != null
    ? Math.round(bio.majority_alignment_rate * 100)
    : null
  const dissentCount = bio?.sole_dissent_count ?? 0
  const dissentCats = bio?.sole_dissent_categories ?? []
  const topDissentCats = dissentCats
    .slice(0, 2)
    .map((c) => c.category.toLowerCase())

  // ── Former member ──────────────────────────────────────────
  if (!record.is_current) {
    const termEnd = record.term_end
      ? new Date(record.term_end + 'T00:00:00').toLocaleDateString('en-US', {
          month: 'long',
          year: 'numeric',
        })
      : null
    return (
      <>
        {firstName} previously served as {roleName}
        {termEnd && <>, leaving office in <strong>{termEnd}</strong></>}.
        {alignmentPct != null && (
          <> {firstName} voted with the council majority <strong>{alignmentPct}%</strong> of the time.</>
        )}
        {dissentCount > 0 && (
          <> {firstName} was the <strong>sole dissenter {dissentCount} time{dissentCount !== 1 ? 's' : ''}</strong>
          {topDissentCats.length > 0 && (
            <> — most often on {formatList(topDissentCats)}</>
          )}.</>
        )}
        {dissentCount === 0 && alignmentPct != null && (
          <> {firstName} never cast a sole dissenting vote.</>
        )}
        {record.meetings_total > 0 && (
          <> Attended <strong>{attendancePct}%</strong> of meetings.</>
        )}
      </>
    )
  }

  // ── Current member, running for different office ───────────
  if (!candidate.is_incumbent) {
    return (
      <>
        {firstName} currently serves as <strong>{roleName}</strong>.
        {alignmentPct != null && (
          <> {firstName} votes with the council majority <strong>{alignmentPct}%</strong> of the time.</>
        )}
        {dissentCount > 0 && (
          <> {firstName} has been the <strong>sole dissenter {dissentCount} time{dissentCount !== 1 ? 's' : ''}</strong>
          {topDissentCats.length > 0 && (
            <> — most often on {formatList(topDissentCats)}</>
          )}.</>
        )}
        {dissentCount === 0 && alignmentPct != null && (
          <> {firstName} has never cast a sole dissenting vote.</>
        )}
        {record.meetings_total > 0 && (
          <> Attended <strong>{attendancePct}%</strong> of meetings.</>
        )}
      </>
    )
  }

  // ── Incumbent running for re-election ──────────────────────
  return (
    <>
      As {roleName}, {firstName} votes with the council majority{' '}
      {alignmentPct != null ? <><strong>{alignmentPct}%</strong> of the time</> : <>on most issues</>}.
      {dissentCount > 0 && (
        <> {firstName} has been the <strong>sole dissenter {dissentCount} time{dissentCount !== 1 ? 's' : ''}</strong>
        {topDissentCats.length > 0 && (
          <> — most often on {formatList(topDissentCats)}</>
        )}.</>
      )}
      {dissentCount === 0 && alignmentPct != null && (
        <> {firstName} has never cast a sole dissenting vote.</>
      )}
      {record.meetings_total > 0 && (
        <> Attended <strong>{attendancePct}%</strong> of meetings.</>
      )}
    </>
  )
}

function formatList(items: string[]): string {
  if (items.length === 0) return ''
  if (items.length === 1) return items[0]
  return `${items[0]} and ${items[1]}`
}

function renderMoneyNarrative(
  candidate: CandidateFundraisingDetail,
  cycleYear: number,
): ReactNode {
  if (candidate.total_raised === 0 && candidate.lifetime_raised === 0) {
    return <>No campaign finance filings have been linked to this candidate.</>
  }

  if (candidate.total_raised === 0) {
    return <>No fundraising has been recorded for this election cycle (since January {cycleYear}).</>
  }

  const firstName = candidate.candidate_name.split(' ')[0]
  const topNames = candidate.top_donors.slice(0, 2).map((d) => d.donor_name)
  const { small, major, total_count } = candidate.contribution_breakdown
  const majorPct = total_count > 0 ? Math.round((major / total_count) * 100) : 0
  const smallPct = total_count > 0 ? Math.round((small / total_count) * 100) : 0

  return (
    <>
      {firstName}&apos;s committee has raised{' '}
      <strong>${fmtNum(candidate.total_raised)}</strong> from{' '}
      <strong>{candidate.donor_count} donor{candidate.donor_count !== 1 ? 's' : ''}</strong>{' '}
      since January {cycleYear}.
      {candidate.avg_contribution > 0 && (
        <> The typical contribution is <strong>${fmtNum(candidate.avg_contribution)}</strong>.</>
      )}
      {topNames.length === 1 && (
        <> The largest supporter is <strong>{topNames[0]}</strong>.</>
      )}
      {topNames.length >= 2 && (
        <> The largest supporters include <strong>{topNames[0]}</strong> and <strong>{topNames[1]}</strong>.</>
      )}
      {majorPct > 50 && (
        <> Most fundraising comes from contributions of <strong>$1,000 or more</strong> ({majorPct}% of contributions).</>
      )}
      {majorPct <= 50 && smallPct > 50 && (
        <> Most contributions are <strong>under $100</strong> ({smallPct}% of all contributions).</>
      )}
    </>
  )
}

function renderPriorActivityNarrative(
  candidate: CandidateFundraisingDetail,
  cycleYear: number,
): ReactNode {
  const priorAmount = candidate.lifetime_raised - candidate.total_raised
  if (priorAmount <= 0) return null

  const earliest = candidate.earliest_contribution
    ? new Date(candidate.earliest_contribution + 'T00:00:00').toLocaleDateString('en-US', {
        month: 'short',
        year: 'numeric',
      })
    : null

  if (earliest) {
    return (
      <>
        The committee previously raised <strong>${fmtNum(priorAmount)}</strong> between{' '}
        {earliest} and January {cycleYear}, under prior election filings.
      </>
    )
  }
  return (
    <>
      The committee has raised <strong>${fmtNum(candidate.lifetime_raised)}</strong> total
      across all election cycles.
    </>
  )
}

function fmtNum(n: number): string {
  return n.toLocaleString('en-US', { maximumFractionDigits: 0 })
}
