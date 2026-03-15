import { getCoalitionData } from '@/lib/queries'
import AlignmentMatrix from '@/components/AlignmentMatrix'
import BlocSummary from '@/components/BlocSummary'
import DivergenceTable from '@/components/DivergenceTable'
import LastUpdated from '@/components/LastUpdated'

export default async function CoalitionDashboard() {
  const { alignments, blocs, divergences, officials } = await getCoalitionData()

  // Extract unique categories from alignments (non-null, sorted)
  const categories = Array.from(
    new Set(alignments.filter((a) => a.category !== null).map((a) => a.category as string))
  ).sort()

  // Summary stats
  const overallAlignments = alignments.filter((a) => a.category === null)
  const totalPairs = overallAlignments.length
  const highlyAligned = overallAlignments.filter((a) => a.agreement_rate >= 0.85 && a.total_shared_votes >= 5).length
  const divergentPairs = overallAlignments.filter((a) => a.agreement_rate < 0.50 && a.total_shared_votes >= 5).length
  const totalVotesAnalyzed = overallAlignments.reduce((sum, a) => sum + a.total_shared_votes, 0)

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-3xl font-bold text-civic-navy mb-2">
        Voting Coalitions
      </h1>
      <p className="text-slate-600 mb-8">
        How the current council votes together, where they diverge, and on which
        topics. Based on contested votes only (where at least one current member
        dissented). Unanimous votes are excluded to reveal actual political dynamics.
      </p>

      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
        <StatCard label="Council Pairs" value={totalPairs.toString()} />
        <StatCard label="Highly Aligned" value={highlyAligned.toString()} sub="85%+ agreement" />
        <StatCard label="Divergent" value={divergentPairs.toString()} sub="<50% agreement" />
        <StatCard label="Contested Votes" value={Math.round(totalVotesAnalyzed / 2).toLocaleString()} sub="non-unanimous only" />
      </div>

      {/* Alignment Matrix */}
      <section className="mb-10">
        <h2 className="text-xl font-semibold text-slate-800 mb-1">
          Alignment Matrix
        </h2>
        <p className="text-sm text-slate-500 mb-4">
          Percentage of contested votes where both members voted the same direction.
          Filter by topic to see where alignment shifts. Hover for details.
        </p>
        <AlignmentMatrix
          alignments={alignments}
          officials={officials}
          categories={categories}
        />
      </section>

      {/* Voting Blocs */}
      <section className="mb-10">
        <h2 className="text-xl font-semibold text-slate-800 mb-1">
          Voting Blocs
        </h2>
        <p className="text-sm text-slate-500 mb-4">
          Groups of 3+ members who are mutually aligned. Strong blocs: 85%+
          agreement across all pairs. Moderate: 70-84%.
        </p>
        <BlocSummary blocs={blocs} />
      </section>

      {/* Category Divergences */}
      <section className="mb-10">
        <h2 className="text-xl font-semibold text-slate-800 mb-1">
          Category Divergences
        </h2>
        <p className="text-sm text-slate-500 mb-4">
          Pairs that agree overall but diverge on specific topics.
          Gap = overall agreement minus topic-specific agreement.
        </p>
        <DivergenceTable divergences={divergences} />
      </section>

      {/* Methodology */}
      <section className="bg-slate-50 rounded-lg border border-slate-200 p-4 text-sm text-slate-600">
        <h3 className="font-semibold text-slate-700 mb-2">Methodology</h3>
        <p className="mb-2">
          <strong>Contested votes only.</strong> This analysis excludes unanimous
          votes (where all members voted the same way). Only motions with at least
          one dissenting vote are included, revealing where council members actually
          disagree rather than inflating agreement rates with routine approvals.
        </p>
        <p className="mb-2">
          <strong>Agreement rate</strong> is the percentage of contested votes where
          both members voted the same direction (both aye or both nay). Absent and
          abstaining members are excluded from the calculation for that motion.
        </p>
        <p className="mb-2">
          <strong>Voting blocs</strong> are detected by checking all possible groups
          of 3+ members for mutual alignment above the threshold. A pair must have at
          least 5 shared contested votes to be included.
        </p>
        <p className="mb-2">
          <strong>Category divergences</strong> highlight topics where a pair&apos;s
          agreement drops 15+ percentage points below their overall rate, on at least
          5 shared topic votes.
        </p>
        <p>
          Alignment percentages reflect recorded votes only. They do not imply
          coordination, shared ideology, or political affiliation.
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
      <p className="text-sm text-slate-600">{label}</p>
      {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
    </div>
  )
}
