import type { Metadata } from 'next'
import { getOfficials } from '@/lib/queries'
import OfficialCard from '@/components/OfficialCard'
import FormerMembersSection from '@/components/FormerMembersSection'
import LastUpdated from '@/components/LastUpdated'

export const revalidate = 3600 // Revalidate every hour

export const metadata: Metadata = {
  title: 'Council Members',
  description: 'Richmond City Council members — current and former officials with voting records and campaign finance data.',
}

export default async function CouncilPage() {
  const officials = await getOfficials(undefined, { councilOnly: true })
  const current = officials.filter((o) => o.is_current)
  const former = officials.filter((o) => !o.is_current)

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      <h1 className="text-4xl font-bold text-civic-navy mb-3">Council Members</h1>
      <p className="text-lg text-slate-600 mb-8">
        Richmond City Council — voting records, attendance, and campaign finance transparency.
      </p>

      {/* Current Council */}
      {current.length > 0 && (
        <section className="mb-12">
          <h2 className="text-2xl font-semibold text-slate-800 mb-5">
            Current Council ({current.length})
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {current.map((o) => (
              <OfficialCard key={o.id} official={o} />
            ))}
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
