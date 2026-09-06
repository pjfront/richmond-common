import { Metadata } from 'next'
import { getCommissions } from '@/lib/queries'
import CommissionCard from '@/components/CommissionCard'

export const metadata: Metadata = {
  title: 'Boards & Commissions',
  description: 'Richmond boards, commissions, and committees with member rosters and appointment tracking.',
}


export default async function CommissionsPage() {
  return <CommissionsContent />
}

async function CommissionsContent() {
  const commissions = await getCommissions()

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-slate-900 mb-2">Boards & Commissions</h1>
        <p className="text-slate-600">
          Browse the boards and commissions in our records. Open a board for its listed members, recorded term dates and source links.
        </p>
      </div>

      {commissions.length === 0 ? (
        <p className="text-slate-500 italic">No commission data available yet.</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {commissions.map((c) => (
            <CommissionCard key={c.id} commission={c} />
          ))}
        </div>
      )}
    </div>
  )
}
