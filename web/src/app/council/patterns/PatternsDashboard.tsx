import { getCrossMeetingPatterns } from '@/lib/queries'
import DonorCategoryTable from '@/components/DonorCategoryTable'
import DonorOverlapTable from '@/components/DonorOverlapTable'
import LastUpdated from '@/components/LastUpdated'

export default async function PatternsDashboard() {
  const { donorPatterns, donorOverlaps, summaryStats } = await getCrossMeetingPatterns()

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-3xl font-bold text-civic-navy mb-2">
        Cross-Meeting Patterns
      </h1>
      <p className="text-slate-600 mb-8">
        Patterns across financial contributions and legislative activity.
        Correlation does not imply causation. All data is from public records.
      </p>

      {/* Summary cards */}
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

      {/* Donor-Category Concentration */}
      <section className="mb-10">
        <h2 className="text-xl font-semibold text-slate-800 mb-1">
          Donor-Category Concentration
        </h2>
        <p className="text-sm text-slate-500 mb-4">
          Donors whose recipients&apos; voting activity is concentrated in specific
          policy categories. Concentration measures what percentage of their
          recipients&apos; votes fall in the top category. Click a row to see the
          full category breakdown.
        </p>
        <DonorCategoryTable patterns={donorPatterns} />
      </section>

      {/* Cross-Official Donor Overlap */}
      <section className="mb-10">
        <h2 className="text-xl font-semibold text-slate-800 mb-1">
          Cross-Official Donor Overlap
        </h2>
        <p className="text-sm text-slate-500 mb-4">
          Donors who contribute to two or more elected officials. Sorted by number
          of recipients and total amount contributed.
        </p>
        <DonorOverlapTable overlaps={donorOverlaps} />
      </section>

      {/* Methodology */}
      <section className="bg-slate-50 rounded-lg border border-slate-200 p-4 text-sm text-slate-600">
        <h3 className="font-semibold text-slate-700 mb-2">Methodology</h3>
        <p className="mb-2">
          <strong>Category concentration</strong> measures what percentage of a
          donor&apos;s recipients&apos; votes fall in their top policy category.
          Only donors with $1,000+ in total contributions and 30%+ concentration
          are shown. This reflects recipients&apos; overall voting patterns, not
          vote-specific donor influence.
        </p>
        <p className="mb-2">
          <strong>Cross-official overlap</strong> identifies donors who contribute
          to two or more officials&apos; committees. Many donors support multiple
          candidates for legitimate reasons (party alignment, civic engagement, etc.).
        </p>
        <p>
          Contribution data comes from NetFile (local) and CAL-ACCESS (state) public
          filings. Vote categories are assigned by AI from agenda item content.
          These patterns are informational and do not imply any improper relationship
          between contributions and legislative action.
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
