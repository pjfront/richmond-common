import type { Metadata } from 'next'
import { getOfficials, getBulkFundraisingStats } from '@/lib/queries'
import OfficialCard from '@/components/OfficialCard'
import FormerMembersSection from '@/components/FormerMembersSection'
import LastUpdated from '@/components/LastUpdated'
import type { Official } from '@/lib/types'

export const revalidate = 3600 // Revalidate every hour

export const metadata: Metadata = {
  title: 'Council Members',
  description: 'Richmond City Council members — current and former officials with voting records and campaign finance data.',
}

/** Sort: Mayor first, Vice Mayor second, rest alphabetical by last name */
function sortCouncilMembers(members: Official[]): Official[] {
  const roleOrder: Record<string, number> = {
    mayor: 0,
    vice_mayor: 1,
    council_member: 2,
  }

  return [...members].sort((a, b) => {
    const ra = roleOrder[a.role] ?? 2
    const rb = roleOrder[b.role] ?? 2
    if (ra !== rb) return ra - rb

    // Same role — alphabetical by last name
    const lastA = a.name.split(/\s+/).pop()?.toLowerCase() ?? ''
    const lastB = b.name.split(/\s+/).pop()?.toLowerCase() ?? ''
    return lastA.localeCompare(lastB)
  })
}

export default async function CouncilPage() {
  const [officials, fundraisingStats] = await Promise.all([
    getOfficials(undefined, { councilOnly: true }),
    getBulkFundraisingStats(),
  ])
  const current = sortCouncilMembers(officials.filter((o) => o.is_current))
  const former = officials.filter((o) => !o.is_current)

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
                />
              )
            })}
          </div>
        </section>
      )}

      {/* Former Members — collapsed by default */}
      {former.length > 0 && (
        <FormerMembersSection officials={former} />
      )}

      {officials.length === 0 && (
        <p className="text-slate-500 italic">No council member data available yet.</p>
      )}
      <LastUpdated />
    </div>
  )
}
