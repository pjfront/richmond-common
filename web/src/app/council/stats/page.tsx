import type { Metadata } from 'next'
import { getCategoryStats, getControversialItems } from '@/lib/queries'
import CategoryStatsTable from '@/components/CategoryStatsTable'
import ControversyLeaderboard from '@/components/ControversyLeaderboard'
import LastUpdated from '@/components/LastUpdated'
import OperatorGate from '@/components/OperatorGate'

// RPC calls can timeout during build; render on request only.
export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Council Stats — Topic Distribution & Controversy',
  description: 'How the Richmond City Council spends its time — topic breakdown, split votes, and controversy scoring across all meetings.',
}

export default async function CouncilStatsPage() {
  return (
    <OperatorGate>
      <CouncilStatsContent />
    </OperatorGate>
  )
}

async function CouncilStatsContent() {
  const [categoryStats, controversialItems] = await Promise.all([
    getCategoryStats(),
    getControversialItems(20),
  ])

  const totalItems = categoryStats.reduce((sum, s) => sum + s.item_count, 0)
  const totalSplitVotes = categoryStats.reduce((sum, s) => sum + s.split_vote_count, 0)
  const totalVotes = categoryStats.reduce((sum, s) => sum + s.vote_count, 0)
  const splitPct = totalVotes > 0 ? Math.round((totalSplitVotes / totalVotes) * 100) : 0

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-3xl font-bold text-civic-navy mb-2">
        Council Stats
      </h1>
      <p className="text-slate-600 mb-8">
        How the Richmond City Council spends its time. Topic distribution, voting
        patterns, and controversy scoring across all extracted meetings.
      </p>

      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
        <StatCard label="Agenda Items" value={totalItems.toLocaleString()} />
        <StatCard label="Total Votes" value={totalVotes.toLocaleString()} />
        <StatCard label="Split Votes" value={totalSplitVotes.toLocaleString()} sub={`${splitPct}% of all votes`} />
        <StatCard label="Topics Tracked" value={categoryStats.length.toString()} />
      </div>

      {/* Category breakdown */}
      <section className="mb-10">
        <h2 className="text-xl font-semibold text-slate-800 mb-1">
          Topic Distribution
        </h2>
        <p className="text-sm text-slate-500 mb-4">
          Agenda items by policy area. Sortable by any column.
        </p>
        <CategoryStatsTable stats={categoryStats} />
      </section>

      {/* Controversy leaderboard */}
      <section className="mb-10">
        <h2 className="text-xl font-semibold text-slate-800 mb-1">
          Most Contested Items
        </h2>
        <p className="text-sm text-slate-500 mb-4">
          Agenda items ranked by controversy score. Score combines vote closeness
          (60%), public comment volume (30%), and procedural complexity (10%).
          Consent calendar items are excluded.
        </p>
        <ControversyLeaderboard items={controversialItems} />
      </section>

      {/* Methodology */}
      <section className="bg-slate-50 rounded-lg border border-slate-200 p-4 text-sm text-slate-600">
        <h3 className="font-semibold text-slate-700 mb-2">Methodology</h3>
        <p className="mb-2">
          <strong>Controversy score</strong> (0-10) is a composite of three signals:
        </p>
        <ul className="list-disc list-inside space-y-1 mb-2">
          <li>
            <strong>Vote split</strong> (up to 6 points): A unanimous 7-0 vote scores 0.
            A close 4-3 vote scores 4.3. The closer the vote, the higher the score.
          </li>
          <li>
            <strong>Public comments</strong> (up to 3 points): Normalized against the
            most-commented item in the same meeting. The item with the most comments
            in a meeting scores 3.
          </li>
          <li>
            <strong>Procedural complexity</strong> (up to 1 point): Items with
            substitute motions, reconsiderations, or multiple motions score 1.
          </li>
        </ul>
        <p>
          All data is extracted from official Richmond City Council meeting minutes.
          Categories are assigned by AI classification and reflect the primary policy
          area of each agenda item.
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
