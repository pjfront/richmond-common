import { notFound } from 'next/navigation'
import Link from 'next/link'
import type { Metadata } from 'next'


import {
  getOfficialBySlug,
  getOfficialWithStats,
  getOfficialVotingRecord,
  getOfficialContributions,
  getPastElectionDates,
  getFinancialConnectionsForOfficial,
  getEconomicInterests,
  getOfficialComparativeStats,
  getOfficialElectionHistory,
} from '@/lib/queries'
import DonorTable from '@/components/DonorTable'
import VotingRecordTable from '@/components/VotingRecordTable'
import BioSummary from '@/components/BioSummary'
import EconomicInterestsTable from '@/components/EconomicInterestsTable'
import OfficialInfluenceSection from '@/components/OfficialInfluenceSection'
import SuggestCorrectionLink from '@/components/SuggestCorrectionLink'
import OperatorGate from '@/components/OperatorGate'
import ComparativeContext from '@/components/ComparativeContext'

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
  const title = `${official.name} — ${formatRole(official.role)}`
  const description = `Voting record, attendance, and campaign finance data for ${official.name}, Richmond City Council.`
  return {
    title,
    description,
    openGraph: {
      title: `${title} | Richmond Commons`,
      description,
      type: 'profile',
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

  const [stats, rawVotes, contributions, electionDates, connectionFlags, interests, comparativeStats, electionHistory] = await Promise.all([
    getOfficialWithStats(official.id),
    getOfficialVotingRecord(official.id),
    getOfficialContributions(official.id),
    getPastElectionDates(),
    getFinancialConnectionsForOfficial(official.id),
    getEconomicInterests(official.id),
    getOfficialComparativeStats(official.id),
    getOfficialElectionHistory(official.id),
  ])

  // Transform nested vote records into flat rows for the table
  const voteRecords = rawVotes.map((v) => {
    const motion = v.motions as unknown as {
      id: string
      motion_text: string
      result: string
      vote_tally: string | null
      all_votes: Array<{ vote_choice: string }>
      agenda_items: {
        id: string
        item_number: string
        title: string
        category: string | null
        topic_label: string | null
        public_comment_count: number
        is_consent_calendar: boolean
        meetings: {
          id: string
          meeting_date: string
          meeting_type: string
        }
      }
    }
    return {
      id: v.id as string,
      vote_choice: v.vote_choice as string,
      meeting_id: motion.agenda_items.meetings.id,
      meeting_date: motion.agenda_items.meetings.meeting_date,
      meeting_type: motion.agenda_items.meetings.meeting_type,
      agenda_item_id: motion.agenda_items.id,
      item_number: motion.agenda_items.item_number,
      item_title: motion.agenda_items.title,
      category: motion.agenda_items.category,
      topic_label: motion.agenda_items.topic_label,
      motion_result: motion.result,
      vote_tally: motion.vote_tally,
      has_nay_votes: (motion.all_votes ?? []).some(av => av.vote_choice === 'nay'),
      public_comment_count: motion.agenda_items.public_comment_count ?? 0,
      is_consent_calendar: motion.agenda_items.is_consent_calendar,
    }
  })

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
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
        {/* Election history + upcoming candidacy */}
        {electionHistory.length > 0 && (() => {
          const past = electionHistory
            .filter(e => e.status === 'elected')
            .sort((a, b) => a.election_date.localeCompare(b.election_date))
          const upcoming = electionHistory
            .filter(e => e.status === 'filed' || e.status === 'qualified')
            .sort((a, b) => a.election_date.localeCompare(b.election_date))
          return (
            <div className="mt-2 space-y-1">
              {past.length > 0 && (
                <p className="text-sm text-slate-500">
                  {past.length === 1
                    ? `First elected ${formatDate(past[0].election_date)} for ${past[0].office_sought}`
                    : `Elected ${past.map(e => `${formatDate(e.election_date)} (${e.office_sought}${e.is_incumbent ? ', re-elected' : ''})`).join(', ')}`
                  }
                </p>
              )}
              {upcoming.map(c => {
                const isCrossOffice = official.role === 'mayor'
                  ? !c.office_sought.includes('Mayor')
                  : c.office_sought.includes('Mayor')
                return (
                  <p key={c.id} className="text-sm font-medium text-civic-amber">
                    {isCrossOffice
                      ? `Running for ${c.office_sought} \u2014 ${formatDate(c.election_date)}`
                      : `Running for re-election \u2014 ${formatDate(c.election_date)}`
                    }
                  </p>
                )
              })}
            </div>
          )
        })()}
      </div>

      {/* Section jump nav */}
      <nav className="flex gap-4 text-sm text-slate-400 mb-6 border-b border-slate-100 pb-3">
        <a href="#summary" className="hover:text-civic-navy transition-colors">Summary</a>
        <a href="#contributions" className="hover:text-civic-navy transition-colors">Contributions</a>
        <a href="#votes" className="hover:text-civic-navy transition-colors">Votes</a>
      </nav>

      {/* Summary — AI-generated voting record narrative */}
      <div id="summary" className="scroll-mt-20" />
      <BioSummary
        bioSummary={official.bio_summary ?? null}
        bioGeneratedAt={official.bio_generated_at ?? null}
        bioModel={official.bio_model ?? null}
        officialName={official.name}
        meetingCount={stats?.meetings_total ?? 0}
      />

      {/* ── Layer 2: Activity Data (T6) ──────────────────────────── */}

      {/* Campaign Contributions — "follow the money" is the first question residents have */}
      <section id="contributions" className="mb-8 scroll-mt-20">
        <h2 className="text-xl font-semibold text-slate-800 mb-3">
          Campaign Contributions
        </h2>
        <p className="text-sm text-slate-500 mb-3">
          Public records filed with the city registrar or state FPPC. Donors are
          sorted by total amount. Richmond adopted electronic filing in 2018.
        </p>
        {/* Comparative Context — donor count & fundraising rank (S14-E4) */}
        {comparativeStats && (
          <ComparativeContext stats={comparativeStats} officialName={official.name} />
        )}
        <DonorTable
          contributions={contributions}
          electionDates={electionDates}
          candidateElectionDates={
            electionHistory
              .map((e) => e.election_date)
              .sort()
          }
        />
      </section>

      {/* Voting Record — activity data (T6) */}
      <section id="votes" className="mb-8 scroll-mt-20">
        <h2 className="text-xl font-semibold text-slate-800 mb-3">
          Voting Record
        </h2>
        <VotingRecordTable votes={voteRecords} />
      </section>

      {/* ── Layer 3: Flagged Findings (T6) ───────────────────────── */}
      {/* Separated from activity data to avoid accusatory framing */}

      {/* Economic Interests (Form 700) — Graduated, Operator Only */}
      <EconomicInterestsTable
        interests={interests}
        officialName={official.name}
      />

      {/* Campaign Finance Context — Operator-only, narrative-based (S14-D1) */}
      <OperatorGate>
        <OfficialInfluenceSection
          officialName={official.name}
          flags={connectionFlags}
        />
      </OperatorGate>

      {/* Correction link — at bottom, not competing with header */}
      <div className="mt-8 pt-6 border-t border-slate-100">
        <SuggestCorrectionLink />
      </div>
    </div>
  )
}
