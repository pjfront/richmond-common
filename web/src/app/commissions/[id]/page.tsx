import { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { getCommission, getCommissionMeetings } from '@/lib/queries'
import { formatCommissionType } from '@/lib/format'
import CommissionRosterTable from '@/components/CommissionRosterTable'
import CommissionMeetingHistory from '@/components/CommissionMeetingHistory'


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
  return <CommissionDetailContent params={params} />
}

async function CommissionDetailContent({ params }: PageProps) {
  const { id } = await params
  const result = await getCommission(id)
  if (!result) notFound()

  const { commission, members } = result
  const meetings = await getCommissionMeetings(id)

  const today = new Date().toISOString().split('T')[0]
  const pastRecordedTerms = members.filter((m) => m.term_end && m.term_end < today).length
  const rosterUrl = commission.website_roster_url?.startsWith('https://') ? commission.website_roster_url : null
  const rosterCheckedAt = commission.last_website_scrape ? new Date(commission.last_website_scrape) : null

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
          <span>{members.length} listed current {members.length === 1 ? 'member' : 'members'}</span>
          {pastRecordedTerms > 0 && <span>{pastRecordedTerms} with past recorded term dates</span>}
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

      {/* Member Roster */}
      <section className="mb-10">
        <h2 className="text-xl font-semibold text-slate-900 mb-2">Listed Current Members</h2>
        <p className="text-sm text-slate-600 mb-2">
          These are the current-member records listed in this archive. Recorded term dates alone do not establish who is serving today or whether a seat is vacant.
        </p>
        {rosterUrl && <a href={rosterUrl} target="_blank" rel="noopener noreferrer"
          className="inline-flex min-h-11 items-center text-sm text-civic-navy underline">Official roster source →</a>}
        {rosterCheckedAt && Number.isFinite(rosterCheckedAt.getTime()) && (
          <p className="text-xs text-slate-500 mb-3">Last roster check: {rosterCheckedAt.toLocaleDateString('en-US', {
            month: 'long', day: 'numeric', year: 'numeric', timeZone: 'America/Los_Angeles',
          })}</p>
        )}
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
