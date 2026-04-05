import { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { getCommission, getCommissionStaleness, getCommissionMeetings } from '@/lib/queries'
import { formatCommissionType } from '@/lib/format'
import CommissionRosterTable from '@/components/CommissionRosterTable'
import CommissionMeetingHistory from '@/components/CommissionMeetingHistory'
import OperatorGate from '@/components/OperatorGate'


interface PageProps {
  params: Promise<{ id: string }>
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { id } = await params
  const result = await getCommission(id)
  if (!result) return { title: 'Commission Not Found' }
  return {
    title: result.commission.name,
    description: `Members and details for the ${result.commission.name}.`,
  }
}

export default async function CommissionDetailPage({ params }: PageProps) {
  return (
    <OperatorGate>
      <CommissionDetailContent params={params} />
    </OperatorGate>
  )
}

async function CommissionDetailContent({ params }: PageProps) {
  const { id } = await params
  const result = await getCommission(id)
  if (!result) notFound()

  const { commission, members } = result
  const [staleness, meetings] = await Promise.all([
    getCommissionStaleness(),
    getCommissionMeetings(id),
  ])
  const thisStaleness = staleness.find((s) => s.commission_id === commission.id)

  const today = new Date().toISOString().split('T')[0]
  const activeMembers = members.filter((m) => !m.term_end || m.term_end >= today)
  const holdoverMembers = members.filter((m) => m.term_end && m.term_end < today)
  const total = commission.num_seats
  const vacancies = total ? Math.max(0, total - activeMembers.length) : 0

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-start gap-3 mb-2">
          <h1 className="text-3xl font-bold text-slate-900">{commission.name}</h1>
          <span className="mt-1 text-xs font-medium px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 whitespace-nowrap">
            {formatCommissionType(commission.commission_type)}
          </span>
        </div>

        <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-slate-600">
          {total && (
            <span>
              {activeMembers.length}/{total} active
              {holdoverMembers.length > 0 && `, ${holdoverMembers.length} holdover`}
              {vacancies > 0 && `, ${vacancies} vacant`}
            </span>
          )}
          {commission.appointment_authority && (
            <span>Appointed by: {commission.appointment_authority}</span>
          )}
          {commission.term_length_years && (
            <span>{commission.term_length_years}-year terms</span>
          )}
          {commission.meeting_schedule && (
            <span>{commission.meeting_schedule}</span>
          )}
          {commission.form700_required && (
            <span className="text-amber-700 font-medium">Form 700 required</span>
          )}
        </div>
      </div>

      {/* Staleness Alert */}
      {thisStaleness && thisStaleness.stale_members > 0 && (
        <div className="mb-6 border border-amber-200 bg-amber-50 rounded-lg p-4">
          <h3 className="font-semibold text-amber-800 mb-1">Roster Staleness Alert</h3>
          <p className="text-sm text-amber-700">
            {thisStaleness.stale_members} of {thisStaleness.total_current_members} members
            have stale website data
            {thisStaleness.max_days_stale && ` (up to ${thisStaleness.max_days_stale} days)`}.
          </p>
          {thisStaleness.stale_member_names && (
            <p className="text-xs text-amber-600 mt-1">
              Affected: {thisStaleness.stale_member_names.join(', ')}
            </p>
          )}
        </div>
      )}

      {/* Member Roster */}
      <section className="mb-10">
        <h2 className="text-xl font-semibold text-slate-900 mb-4">Current Members</h2>
        <CommissionRosterTable members={members} />
      </section>

      {/* Meeting History */}
      <section>
        <h2 className="text-xl font-semibold text-slate-900 mb-4">Meeting History</h2>
        <CommissionMeetingHistory meetings={meetings} />
      </section>
    </div>
  )
}
