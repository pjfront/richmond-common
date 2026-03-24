import { notFound } from 'next/navigation'
import Link from 'next/link'
import type { Metadata } from 'next'

export const revalidate = 3600 // Revalidate every hour

import {
  getOfficialBySlug,
  getOfficialWithStats,
  getOfficialVotingRecord,
  getTopDonors,
  getFinancialConnectionsForOfficial,
  getEconomicInterests,
  getOfficialComparativeStats,
} from '@/lib/queries'
import DonorTable from '@/components/DonorTable'
import VotingRecordTable from '@/components/VotingRecordTable'
import BioSummary from '@/components/BioSummary'
import FactualProfile from '@/components/FactualProfile'
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
  return {
    title: `${official.name} — ${formatRole(official.role)}`,
    description: `Voting record, attendance, and campaign finance data for ${official.name}, Richmond City Council.`,
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

  const [stats, rawVotes, donors, connectionFlags, interests, comparativeStats] = await Promise.all([
    getOfficialWithStats(official.id),
    getOfficialVotingRecord(official.id),
    getTopDonors(official.id),
    getFinancialConnectionsForOfficial(official.id),
    getEconomicInterests(official.id),
    getOfficialComparativeStats(official.id),
  ])

  // Transform nested vote records into flat rows for the table
  const voteRecords = rawVotes.map((v) => {
    const motion = v.motions as unknown as {
      id: string
      motion_text: string
      result: string
      vote_tally: string | null
      agenda_items: {
        id: string
        item_number: string
        title: string
        category: string | null
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
      item_number: motion.agenda_items.item_number,
      item_title: motion.agenda_items.title,
      category: motion.agenda_items.category,
      motion_result: motion.result,
      vote_tally: motion.vote_tally,
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
          {official.seat && <span>{official.seat}</span>}
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
        <div className="mt-2">
          <SuggestCorrectionLink />
        </div>
      </div>

      {/* Factual Profile — role context before any data (T6) */}
      <FactualProfile bioFactual={official.bio_factual ?? null} />

      {/* AI Bio Summary (Graduated, Operator Only) */}
      <BioSummary
        bioSummary={official.bio_summary ?? null}
        bioGeneratedAt={official.bio_generated_at ?? null}
        bioModel={official.bio_model ?? null}
        officialName={official.name}
        meetingCount={stats?.meetings_total ?? 0}
      />

      {/* ── Layer 2: Activity Data (T6) ──────────────────────────── */}

      {/* Stats Bar — 3 KPIs per U3 */}
      {stats && (
        <div className="grid grid-cols-3 gap-4 mb-8">
          <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
            <p className="text-2xl font-bold text-civic-navy">{stats.vote_count}</p>
            <p className="text-xs text-slate-500 mt-1">Votes Tracked</p>
          </div>
          <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
            <p className="text-2xl font-bold text-civic-navy">
              {Math.round(stats.attendance_rate * 100)}%
            </p>
            <p className="text-xs text-slate-500 mt-1">
              Attendance ({stats.meetings_attended}/{stats.meetings_total})
            </p>
          </div>
          <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
            <p className="text-2xl font-bold text-civic-navy">{donors.length}</p>
            <p className="text-xs text-slate-500 mt-1">Unique Donors</p>
          </div>
        </div>
      )}

      {/* Comparative Context — CalMatters-style framing (S14-E4) */}
      {comparativeStats && (
        <ComparativeContext stats={comparativeStats} officialName={official.name} />
      )}

      {/* Voting Record — activity before findings (T6) */}
      <section className="mb-8">
        <h2 className="text-xl font-semibold text-slate-800 mb-3">
          Voting Record
        </h2>
        <VotingRecordTable votes={voteRecords} />
      </section>

      {/* Top Donors — campaign finance is activity context, not a finding */}
      <section className="mb-8">
        <h2 className="text-xl font-semibold text-slate-800 mb-3">
          Campaign Contributions
        </h2>
        <p className="text-sm text-slate-500 mb-3">
          All contributions are public records filed with the city registrar or state FPPC.
        </p>
        <DonorTable donors={donors} />
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
    </div>
  )
}
