'use client'

import { useMemo, useState } from 'react'
import AlignmentMatrix from '@/components/AlignmentMatrix'
import BlocSummary from '@/components/BlocSummary'
import DivergenceTable from '@/components/DivergenceTable'
import DivergentMotionsTable from '@/components/DivergentMotionsTable'
import LastUpdated from '@/components/LastUpdated'
import MemberPicker from '@/components/MemberPicker'
import type {
  CategoryDivergence,
  DivergentMotion,
  PairwiseAlignment,
  VotingBloc,
} from '@/lib/types'

interface VotingPatternsDashboardProps {
  alignments: PairwiseAlignment[]
  blocs: VotingBloc[]
  divergences: CategoryDivergence[]
  coalitionOfficials: Array<{ id: string; name: string }>
  motions: DivergentMotion[]
  motionOfficials: Array<{ id: string; name: string }>
}

export default function VotingPatternsDashboard({
  alignments,
  blocs,
  divergences,
  coalitionOfficials,
  motions,
  motionOfficials,
}: VotingPatternsDashboardProps) {
  const [includeProcedural, setIncludeProcedural] = useState(false)
  const [selectedOfficials, setSelectedOfficials] = useState<Set<string>>(
    () => new Set(motionOfficials.map((o) => o.id)),
  )

  const filteredMotions = useMemo(() => {
    return motions.filter((m) => {
      if (!includeProcedural && m.is_procedural) return false
      if (selectedOfficials.size === motionOfficials.length) return true
      // When a strict subset is selected, only show motions where the selected
      // members actually split among themselves.
      const choices = new Set<string>()
      for (const id of selectedOfficials) {
        const choice = m.votes[id]
        if (choice === 'aye' || choice === 'nay') choices.add(choice)
      }
      return choices.size >= 2
    })
  }, [motions, motionOfficials, includeProcedural, selectedOfficials])

  // Categories for the alignment matrix filter (non-null, sorted)
  const categories = useMemo(
    () =>
      Array.from(
        new Set(alignments.filter((a) => a.category !== null).map((a) => a.category as string)),
      ).sort(),
    [alignments],
  )

  // Stats from the overall (category=null) alignments
  const overallAlignments = alignments.filter((a) => a.category === null)
  const totalPairs = overallAlignments.length
  const highlyAligned = overallAlignments.filter(
    (a) => a.agreement_rate >= 0.85 && a.total_shared_votes >= 5,
  ).length
  const divergentPairs = overallAlignments.filter(
    (a) => a.agreement_rate < 0.5 && a.total_shared_votes >= 5,
  ).length
  const totalSplitVotes = motions.length

  const proceduralCount = motions.filter((m) => m.is_procedural).length

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-3xl font-bold text-civic-navy mb-2">
        How the Council Votes
      </h1>
      <p className="text-slate-600 mb-8 max-w-3xl">
        See where your council members vote together, where they split, and on
        which issues. Based on roll-call votes from official meeting minutes.
        Unanimous votes are set aside so the actual disagreements stand out.
      </p>

      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-10">
        <StatCard label="Members compared" value={totalPairs.toString()} sub="Pairs of members" />
        <StatCard
          label="Often vote together"
          value={highlyAligned.toString()}
          sub="Pairs that agree 85%+ of the time"
        />
        <StatCard
          label="Often vote apart"
          value={divergentPairs.toString()}
          sub="Pairs that agree under 50% of the time"
        />
        <StatCard
          label="Split votes"
          value={totalSplitVotes.toLocaleString()}
          sub="Where members didn't agree"
        />
      </div>

      {/* ── Section 1: Where members split (Leisa's headline ask) ─── */}
      <section className="mb-12">
        <h2 className="text-2xl font-semibold text-slate-800 mb-2">
          Where members split
        </h2>
        <p className="text-sm text-slate-600 mb-4 max-w-3xl">
          Each row is a vote where the council didn&apos;t agree. Pick which
          members to compare, and choose whether to include procedural votes
          (motions to extend the meeting, refer items to committee, and other
          steps that aren&apos;t about the underlying issue).
        </p>

        {/* Controls */}
        <div className="flex flex-col gap-3 mb-4 p-4 bg-slate-50 rounded-lg border border-slate-200">
          <MemberPicker
            officials={motionOfficials}
            selected={selectedOfficials}
            onChange={setSelectedOfficials}
          />
          <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
            <input
              type="checkbox"
              checked={includeProcedural}
              onChange={(e) => setIncludeProcedural(e.target.checked)}
              className="w-4 h-4 rounded border-slate-300 text-civic-navy focus:ring-civic-navy"
            />
            <span>
              Include procedural votes
              {proceduralCount > 0 && (
                <span className="text-slate-500 text-xs ml-1">
                  ({proceduralCount} on file)
                </span>
              )}
            </span>
            <span className="text-xs text-slate-500 ml-1">
              — useful for spotting who tries to delay or skip items
            </span>
          </label>
        </div>

        <p className="text-xs text-slate-500 mb-3">
          Showing {filteredMotions.length} {filteredMotions.length === 1 ? 'vote' : 'votes'}
          {!includeProcedural && proceduralCount > 0 && (
            <span> · {proceduralCount} procedural votes hidden</span>
          )}
        </p>

        <DivergentMotionsTable
          motions={filteredMotions}
          officials={motionOfficials}
          selectedOfficials={selectedOfficials}
        />
      </section>

      {/* ── Section 2: Who usually votes the same way ──────────────── */}
      <section className="mb-12">
        <h2 className="text-2xl font-semibold text-slate-800 mb-2">
          Who usually votes the same way
        </h2>
        <p className="text-sm text-slate-600 mb-4 max-w-3xl">
          Each cell shows the share of split votes where two members voted the
          same direction. Filter by topic to see if alignment shifts. Hover for
          details.
        </p>
        <AlignmentMatrix
          alignments={alignments}
          officials={coalitionOfficials}
          categories={categories}
        />
      </section>

      {/* ── Section 3: Voting groups ───────────────────────────────── */}
      <section className="mb-12">
        <h2 className="text-2xl font-semibold text-slate-800 mb-2">
          Voting groups
        </h2>
        <p className="text-sm text-slate-600 mb-4 max-w-3xl">
          Groups of three or more members who tend to vote the same way on
          split votes. Tight groups: 85%+ agreement across every pair. Loose
          groups: 70–84%.
        </p>
        <BlocSummary blocs={blocs} />
      </section>

      {/* ── Section 4: Where pairs disagree on specific topics ─────── */}
      <section className="mb-12">
        <h2 className="text-2xl font-semibold text-slate-800 mb-2">
          Where pairs disagree on specific topics
        </h2>
        <p className="text-sm text-slate-600 mb-4 max-w-3xl">
          Pairs of members who usually agree overall, but disagree more often
          on a specific topic. The gap is how much lower their agreement drops
          on that topic.
        </p>
        <DivergenceTable divergences={divergences} />
      </section>

      {/* Methodology */}
      <section className="bg-slate-50 rounded-lg border border-slate-200 p-5 text-sm text-slate-600">
        <h3 className="font-semibold text-slate-700 mb-3">How this is built</h3>
        <p className="mb-2">
          <strong>Split votes only.</strong> This page sets aside votes where
          everyone agreed. Only motions with at least one yes and one no vote
          are included, so you can see where members actually take different
          positions.
        </p>
        <p className="mb-2">
          <strong>Agreement rate</strong> is the share of split votes where
          two members voted the same direction. Members who were absent or
          abstained on a given motion are not counted in that motion.
        </p>
        <p className="mb-2">
          <strong>Procedural votes</strong> are motions about how the meeting
          runs (extending the meeting, referring items to committee, limiting
          public comment), not about the underlying issue. They&apos;re hidden
          by default. Toggle them on to spot patterns like running out the
          clock on contested items.
        </p>
        <p className="mb-2">
          <strong>Voting groups</strong> are detected by checking every group
          of 3+ members for mutual agreement above the threshold. A pair must
          have at least 5 shared split votes to count.
        </p>
        <p className="mb-2">
          <strong>Topic-specific disagreements</strong> highlight pairs whose
          agreement drops 15+ percentage points on a specific topic compared
          to their overall rate, on at least 5 topic-specific votes.
        </p>
        <p>
          Vote records come from official meeting minutes. Agreement rates
          reflect recorded votes only — they don&apos;t imply coordination,
          shared ideology, or political affiliation.
        </p>
      </section>

      <LastUpdated />
    </div>
  )
}

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <p className="text-2xl font-bold text-civic-navy tabular-nums">{value}</p>
      <p className="text-sm text-slate-700 mt-1">{label}</p>
      {sub && <p className="text-xs text-slate-500 mt-1">{sub}</p>}
    </div>
  )
}
