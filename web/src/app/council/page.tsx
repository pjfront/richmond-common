import type { Metadata } from 'next'
import { getOfficials, getCurrentCandidacies } from '@/lib/queries'
import OfficialCard from '@/components/OfficialCard'
import LastUpdated from '@/components/LastUpdated'

export const dynamic = 'force-dynamic'
export const revalidate = 3600 // Revalidate every hour

export const metadata: Metadata = {
  title: 'Council Members',
  description: 'Richmond City Council members — current and former officials with voting records and campaign finance data.',
}

export default async function CouncilPage() {
  const [officials, candidacies] = await Promise.all([
    getOfficials(undefined, { councilOnly: true }),
    getCurrentCandidacies(),
  ])
  const current = officials.filter((o) => o.is_current)

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
      <p className="text-base text-slate-600 mb-8">
        Richmond&apos;s seven elected council members.
      </p>

      {current.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {current.map((o) => (
            <OfficialCard
              key={o.id}
              official={o}
              candidacy={candidacyMap.get(o.id)}
            />
          ))}
        </div>
      )}

      {/* Former Members — hidden until data quality cleanup (D30) */}

      {officials.length === 0 && (
        <p className="text-slate-500 italic">No council member data available yet.</p>
      )}
      <LastUpdated />
    </div>
  )
}
