import type { Metadata } from 'next'
import { getOfficials, getBulkFundraisingStats, getCurrentCandidacies, type CycleFundraisingStats } from '@/lib/queries'
import OfficialCard from '@/components/OfficialCard'
import FormerMembersSection from '@/components/FormerMembersSection'
import LastUpdated from '@/components/LastUpdated'
import type { Official } from '@/lib/types'

export const dynamic = 'force-dynamic'
export const revalidate = 3600 // Revalidate every hour

export const metadata: Metadata = {
  title: 'Council Members',
  description: 'Richmond City Council members — current and former officials with voting records and campaign finance data.',
}

/** Sort by all-time fundraising total, descending */
function sortByFundraising(
  members: Official[],
  stats: Map<string, CycleFundraisingStats>,
): Official[] {
  return [...members].sort((a, b) => {
    const totalA = stats.get(a.id)?.allTime.total ?? 0
    const totalB = stats.get(b.id)?.allTime.total ?? 0
    return totalB - totalA
  })
}

export default async function CouncilPage() {
  const [officials, fundraisingStats, candidacies] = await Promise.all([
    getOfficials(undefined, { councilOnly: true }),
    getBulkFundraisingStats(),
    getCurrentCandidacies(),
  ])
  const current = sortByFundraising(officials.filter((o) => o.is_current), fundraisingStats)
  const former = officials.filter((o) => !o.is_current)

  // Build a map: official_id -> upcoming candidacy info
  const candidacyMap = new Map<string, { office: string; electionDate: string }>()
  for (const c of candidacies) {
    if (c.official_id) {
      candidacyMap.set(c.official_id, { office: c.office_sought, electionDate: c.election_date })
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      <h1 className="text-4xl font-bold text-civic-navy mb-3">Council Members</h1>
      <p className="text-lg text-slate-600 mb-8">
        Richmond City Council — voting records, attendance, and campaign finance transparency.
      </p>

      {/* Current Council — single column, larger cards */}
      {current.length > 0 && (
        <section className="mb-12">
          <h2 className="text-2xl font-semibold text-slate-800 mb-5">
            Current Council ({current.length})
          </h2>
          <div className="space-y-4">
            {current.map((o) => {
              const stats = fundraisingStats.get(o.id)
              return (
                <OfficialCard
                  key={o.id}
                  official={o}
                  fundraisingStats={stats}
                  candidacy={candidacyMap.get(o.id)}
                />
              )
            })}
          </div>
        </section>
      )}

      {/* Former Members — hidden until data quality cleanup (D29) */}

      {officials.length === 0 && (
        <p className="text-slate-500 italic">No council member data available yet.</p>
      )}
      <LastUpdated />
    </div>
  )
}
