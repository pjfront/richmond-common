import { Metadata } from 'next'
import { getCommissions } from '@/lib/queries'
import CommissionCard from '@/components/CommissionCard'

export const metadata: Metadata = {
  title: 'Boards & Commissions',
  description: 'Richmond boards, commissions, and committees with member rosters and appointment tracking.',
}

export const revalidate = 3600

export default async function CommissionsPage() {
  const commissions = await getCommissions()

  const totalSeats = commissions.reduce((sum, c) => sum + (c.num_seats ?? 0), 0)
  const totalFilled = commissions.reduce((sum, c) => sum + c.member_count, 0)
  const totalVacancies = commissions.reduce((sum, c) => sum + c.vacancy_count, 0)
  const form700Count = commissions.filter((c) => c.form700_required).length

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-slate-900 mb-2">Boards & Commissions</h1>
        <p className="text-slate-600">
          Richmond has {commissions.length} boards and commissions with {totalFilled} of {totalSeats} seats filled.
          {totalVacancies > 0 && ` ${totalVacancies} vacancies across all bodies.`}
          {form700Count > 0 && ` ${form700Count} require Form 700 financial disclosure.`}
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
