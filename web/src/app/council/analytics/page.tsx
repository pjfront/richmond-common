/**
 * Consolidated council analytics page.
 *
 * Phase 2.6 of the re-architecture folded three previously-separate routes
 * into this single tabbed surface:
 *
 *   /council/voting-patterns  →  /council/analytics            (default tab)
 *   /council/stats            →  /council/analytics?tab=stats
 *   /council/patterns         →  /council/analytics?tab=patterns
 *
 * Static 308 redirects for the old URLs live in `next.config.ts`.
 *
 * Why tabs are <Link>s and not JS state: link-based switching is fully
 * server-rendered, indexable per-tab, and accessible without JS. The trade-
 * off is a server roundtrip per tab change — acceptable for an operator-
 * mostly page where switches are rare.
 *
 * Why force-dynamic: the underlying RPCs (get_coalition_data,
 * get_divergent_motions_detail) exceed the anon statement_timeout under
 * concurrent build prerenders. force-dynamic mirrors the old voting-patterns
 * page's documented workaround. Stats + patterns are fast enough on their
 * own but we serve them all from the same page so they share the config.
 */
import type { Metadata } from 'next'
import {
  getCoalitionData,
  getDivergentMotions,
  getCategoryStats,
  getControversialItems,
  getCrossMeetingPatterns,
} from '@/lib/queries'
import VotingPatternsDashboard from './VotingPatternsDashboard'
import CategoryStatsTable from '@/components/CategoryStatsTable'
import ControversyLeaderboard from '@/components/ControversyLeaderboard'
import DonorCategoryTable from '@/components/DonorCategoryTable'
import DonorOverlapTable from '@/components/DonorOverlapTable'
import DonorOverlapSelector from '@/components/DonorOverlapSelector'
import LastUpdated from '@/components/LastUpdated'
import OperatorGate from '@/components/OperatorGate'
import AnalyticsTabs, { type AnalyticsTab } from './AnalyticsTabs'

export const dynamic = 'force-dynamic'
export const maxDuration = 60

export const metadata: Metadata = {
  title: 'Council Analytics',
  description:
    'How the Richmond City Council votes, what topics dominate the agenda, and where donor patterns concentrate.',
}

interface PageProps {
  searchParams: Promise<{ tab?: string }>
}

function normalizeTab(raw: string | undefined): AnalyticsTab {
  if (raw === 'stats' || raw === 'patterns') return raw
  return 'voting'
}

export default async function CouncilAnalyticsPage({ searchParams }: PageProps) {
  const { tab } = await searchParams
  const activeTab = normalizeTab(tab)

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <header className="mb-4">
        <h1 className="text-3xl font-bold text-civic-navy">Council Analytics</h1>
        <p className="text-slate-600 mt-1">
          How the Richmond City Council votes, what topics dominate the agenda, and where donor
          patterns concentrate.
        </p>
      </header>

      <AnalyticsTabs activeTab={activeTab} />

      {activeTab === 'voting' && <VotingTabContent />}

      {activeTab === 'stats' && (
        <OperatorGate>
          <StatsTabContent />
        </OperatorGate>
      )}

      {activeTab === 'patterns' && (
        <OperatorGate>
          <PatternsTabContent />
        </OperatorGate>
      )}
    </div>
  )
}

// ─── Voting tab ─────────────────────────────────────────────────

async function VotingTabContent() {
  const [coalition, divergent] = await Promise.all([
    getCoalitionData(),
    getDivergentMotions(),
  ])
  return (
    <VotingPatternsDashboard
      alignments={coalition.alignments}
      coalitionOfficials={coalition.officials}
      motions={divergent.motions}
      motionOfficials={divergent.officials}
    />
  )
}

// ─── Stats tab (formerly /council/stats) ────────────────────────

async function StatsTabContent() {
  let categoryStats: Awaited<ReturnType<typeof getCategoryStats>> = []
  let controversialItems: Awaited<ReturnType<typeof getControversialItems>> = []
  try {
    const [c, ci] = await Promise.all([
      getCategoryStats(),
      getControversialItems(20),
    ])
    categoryStats = c
    controversialItems = ci
  } catch (err) {
    console.error('[council/analytics:stats] data fetch failed, rendering empty state:', err)
  }

  const totalItems = categoryStats.reduce((sum, s) => sum + s.item_count, 0)
  const totalSplitVotes = categoryStats.reduce((sum, s) => sum + s.split_vote_count, 0)
  const totalVotes = categoryStats.reduce((sum, s) => sum + s.vote_count, 0)
  const splitPct = totalVotes > 0 ? Math.round((totalSplitVotes / totalVotes) * 100) : 0

  return (
    <div>
      <p className="text-sm text-slate-500 mb-6">
        Topic distribution, voting patterns, and controversy scoring across all extracted meetings.
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
        <StatCard label="Agenda Items" value={totalItems.toLocaleString()} />
        <StatCard label="Total Votes" value={totalVotes.toLocaleString()} />
        <StatCard
          label="Split Votes"
          value={totalSplitVotes.toLocaleString()}
          sub={`${splitPct}% of all votes`}
        />
        <StatCard label="Topics Tracked" value={categoryStats.length.toString()} />
      </div>

      <section className="mb-10">
        <h2 className="text-xl font-semibold text-slate-800 mb-1">Topic Distribution</h2>
        <p className="text-sm text-slate-500 mb-4">
          Agenda items by policy area. Sortable by any column.
        </p>
        <CategoryStatsTable stats={categoryStats} />
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-semibold text-slate-800 mb-1">Most Contested Items</h2>
        <p className="text-sm text-slate-500 mb-4">
          Agenda items ranked by controversy score. Score combines vote closeness (60%), public
          comment volume (30%), and procedural complexity (10%). Consent calendar items are
          excluded.
        </p>
        <ControversyLeaderboard items={controversialItems} />
      </section>

      <section className="bg-slate-50 rounded-lg border border-slate-200 p-4 text-sm text-slate-600">
        <h3 className="font-semibold text-slate-700 mb-2">Methodology</h3>
        <p className="mb-2">
          <strong>Controversy score</strong> (0-10) is a composite of three signals:
        </p>
        <ul className="list-disc list-inside space-y-1 mb-2">
          <li>
            <strong>Vote split</strong> (up to 6 points): A unanimous 7-0 vote scores 0. A close 4-3
            vote scores 4.3. The closer the vote, the higher the score.
          </li>
          <li>
            <strong>Public comments</strong> (up to 3 points): Normalized against the most-commented
            item in the same meeting. The item with the most comments in a meeting scores 3.
          </li>
          <li>
            <strong>Procedural complexity</strong> (up to 1 point): Items with substitute motions,
            reconsiderations, or multiple motions score 1.
          </li>
        </ul>
        <p>
          All data is extracted from official Richmond City Council meeting minutes. Categories are
          assigned by AI classification and reflect the primary policy area of each agenda item.
        </p>
      </section>

      <LastUpdated />
    </div>
  )
}

// ─── Patterns tab (formerly /council/patterns) ──────────────────

async function PatternsTabContent() {
  const { donorPatterns, donorOverlaps, summaryStats } = await getCrossMeetingPatterns()

  return (
    <div>
      <p className="text-sm text-slate-500 mb-6">
        Patterns across financial contributions and legislative activity. Correlation does not imply
        causation. All data is from public records.
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
        <StatCard label="Unique Donors" value={summaryStats.totalDonors.toLocaleString()} />
        <StatCard
          label="Concentrated"
          value={summaryStats.concentratedDonors.toString()}
          sub="category-focused donors"
        />
        <StatCard
          label="Multi-Recipient"
          value={summaryStats.multiRecipientDonors.toString()}
          sub="donors to 2+ officials"
        />
        <StatCard
          label="Contributions"
          value={summaryStats.totalContributions.toLocaleString()}
          sub="individual records"
        />
      </div>

      <section className="mb-10">
        <h2 className="text-xl font-semibold text-slate-800 mb-1">Donor-Category Concentration</h2>
        <p className="text-sm text-slate-500 mb-4">
          Donors whose recipients&apos; voting activity is concentrated in specific policy
          categories. Concentration measures what percentage of their recipients&apos; votes fall in
          the top category. Click a row to see the full category breakdown.
        </p>
        <DonorCategoryTable patterns={donorPatterns} />
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-semibold text-slate-800 mb-1">Shared Donors</h2>
        <p className="text-sm text-slate-500 mb-4">
          Select council members to see which donors they have in common. Many donors support
          multiple candidates for legitimate reasons.
        </p>
        <DonorOverlapSelector overlaps={donorOverlaps} />
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-semibold text-slate-800 mb-1">All Cross-Official Donors</h2>
        <p className="text-sm text-slate-500 mb-4">
          Every donor who contributes to two or more elected officials.
        </p>
        <DonorOverlapTable overlaps={donorOverlaps} />
      </section>

      <section className="bg-slate-50 rounded-lg border border-slate-200 p-4 text-sm text-slate-600">
        <h3 className="font-semibold text-slate-700 mb-2">Methodology</h3>
        <p className="mb-2">
          <strong>Category concentration</strong> measures what percentage of a donor&apos;s
          recipients&apos; votes fall in their top policy category. Only donors with $1,000+ in
          total contributions and 30%+ concentration are shown. This reflects recipients&apos;
          overall voting patterns, not vote-specific donor influence.
        </p>
        <p className="mb-2">
          <strong>Cross-official overlap</strong> identifies donors who contribute to two or more
          officials&apos; committees. Many donors support multiple candidates for legitimate reasons
          (party alignment, civic engagement, etc.).
        </p>
        <p>
          Contribution data comes from NetFile (local) and CAL-ACCESS (state) public filings. Vote
          categories are assigned by AI from agenda item content. These patterns are informational
          and do not imply any improper relationship between contributions and legislative action.
        </p>
      </section>

      <LastUpdated />
    </div>
  )
}

// ─── Shared ─────────────────────────────────────────────────────

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <p className="text-2xl font-bold text-civic-navy tabular-nums">{value}</p>
      <p className="text-sm text-slate-600">{label}</p>
      {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
    </div>
  )
}
