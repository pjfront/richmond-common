import { notFound } from 'next/navigation'
import Link from 'next/link'
import type { Metadata } from 'next'
import { getMeeting, getConflictFlags } from '@/lib/queries'
import AttendanceRoster from '@/components/AttendanceRoster'
import AgendaItemCard from '@/components/AgendaItemCard'

function formatDate(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

export async function generateMetadata(
  { params }: { params: Promise<{ id: string }> }
): Promise<Metadata> {
  const { id } = await params
  const meeting = await getMeeting(id)
  if (!meeting) return { title: 'Meeting Not Found' }
  return {
    title: `${formatDate(meeting.meeting_date)} Meeting`,
    description: `Richmond City Council ${meeting.meeting_type} meeting on ${formatDate(meeting.meeting_date)}.`,
  }
}

export default async function MeetingDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  const meeting = await getMeeting(id)
  if (!meeting) notFound()

  const flags = await getConflictFlags(id)
  const publishedFlags = flags.filter((f) => f.confidence >= 0.5)

  const consentItems = meeting.agenda_items.filter((i) => i.is_consent_calendar)
  const regularItems = meeting.agenda_items.filter((i) => !i.is_consent_calendar)

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-6">
        <Link href="/meetings" className="text-sm text-civic-navy-light hover:text-civic-navy">
          &larr; All Meetings
        </Link>
        <h1 className="text-3xl font-bold text-civic-navy mt-2">
          {formatDate(meeting.meeting_date)}
        </h1>
        <div className="flex gap-4 mt-2 text-sm text-slate-600">
          <span className="capitalize">{meeting.meeting_type} Meeting</span>
          {meeting.presiding_officer && <span>Presiding: {meeting.presiding_officer}</span>}
          {meeting.call_to_order_time && <span>Called to order: {meeting.call_to_order_time}</span>}
        </div>
      </div>

      {/* Conflict Flag Callout */}
      {publishedFlags.length > 0 && (
        <div className="bg-civic-amber/10 border border-civic-amber/30 rounded-lg p-4 mb-6">
          <h3 className="font-semibold text-civic-amber">
            {publishedFlags.length} Transparency Flag{publishedFlags.length !== 1 ? 's' : ''}
          </h3>
          <p className="text-sm text-slate-700 mt-1">
            The conflict scanner identified potential financial connections for this meeting.{' '}
            <Link href={`/reports/${id}`} className="text-civic-navy-light underline">
              View full report
            </Link>
          </p>
        </div>
      )}

      {/* Attendance */}
      <div className="mb-6">
        <AttendanceRoster attendance={meeting.attendance} />
      </div>

      {/* Consent Calendar */}
      {consentItems.length > 0 && (
        <section className="mb-8">
          <h2 className="text-xl font-semibold text-slate-800 mb-3">
            Consent Calendar ({consentItems.length} items)
          </h2>
          <p className="text-sm text-slate-500 mb-3">
            Items approved as a group. Click to expand individual items.
          </p>
          <div className="space-y-2">
            {consentItems.map((item) => (
              <AgendaItemCard key={item.id} item={item} />
            ))}
          </div>
        </section>
      )}

      {/* Regular Agenda */}
      {regularItems.length > 0 && (
        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-3">
            Agenda Items ({regularItems.length})
          </h2>
          <div className="space-y-2">
            {regularItems.map((item) => (
              <AgendaItemCard key={item.id} item={item} />
            ))}
          </div>
        </section>
      )}

      {/* Summary stats */}
      <div className="mt-8 text-sm text-slate-400">
        {meeting.agenda_items.length} items | {meeting.agenda_items.reduce((sum, i) => sum + i.motions.length, 0)} motions |{' '}
        {meeting.agenda_items.reduce((sum, i) => sum + i.motions.reduce((s, m) => s + m.votes.length, 0), 0)} votes recorded
      </div>
    </div>
  )
}
