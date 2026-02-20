import type { Metadata } from 'next'
import { getOfficials } from '@/lib/queries'
import OfficialCard from '@/components/OfficialCard'

export const metadata: Metadata = {
  title: 'Council Members',
  description: 'Richmond City Council members — current and former officials with voting records and campaign finance data.',
}

export default async function CouncilPage() {
  const officials = await getOfficials()
  const current = officials.filter((o) => o.is_current)
  const former = officials.filter((o) => !o.is_current)

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-3xl font-bold text-civic-navy mb-2">Council Members</h1>
      <p className="text-slate-600 mb-8">
        Richmond City Council — voting records, attendance, and campaign finance transparency.
      </p>

      {/* Current Council */}
      {current.length > 0 && (
        <section className="mb-10">
          <h2 className="text-xl font-semibold text-slate-800 mb-4">
            Current Council ({current.length})
          </h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {current.map((o) => (
              <OfficialCard key={o.id} official={o} />
            ))}
          </div>
        </section>
      )}

      {/* Former Members */}
      {former.length > 0 && (
        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-4">
            Former Members ({former.length})
          </h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {former.map((o) => (
              <OfficialCard key={o.id} official={o} />
            ))}
          </div>
        </section>
      )}

      {officials.length === 0 && (
        <p className="text-slate-500 italic">No council member data available yet.</p>
      )}
    </div>
  )
}
