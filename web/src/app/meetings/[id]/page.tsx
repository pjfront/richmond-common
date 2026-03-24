import { notFound } from 'next/navigation'
import Link from 'next/link'
import type { Metadata } from 'next'
import { getMeeting, getConflictFlags } from '@/lib/queries'
import { CONFIDENCE_PUBLISHED } from '@/lib/thresholds'
import AttendanceRoster from '@/components/AttendanceRoster'
import MeetingTypeBadge from '@/components/MeetingTypeBadge'
import MeetingDetailClient from '@/components/MeetingDetailClient'
import RecordVisit from '@/components/RecordVisit'
import OperatorGate from '@/components/OperatorGate'

export const revalidate = 3600 // Revalidate every hour

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
  const publishedFlags = flags.filter((f) => f.confidence >= CONFIDENCE_PUBLISHED)

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      <OperatorGate>
        <RecordVisit
          type="meeting"
          id={id}
          title={`${formatDate(meeting.meeting_date)} ${meeting.meeting_type}`}
          url={`/meetings/${id}`}
        />
      </OperatorGate>
      {/* Header */}
      <div className="mb-6">
        <Link href="/meetings" className="text-sm text-civic-navy-light hover:text-civic-navy">
          &larr; All Meetings
        </Link>
        <div className="flex items-center gap-3 mt-2">
          <h1 className="text-4xl font-bold text-civic-navy">
            {formatDate(meeting.meeting_date)}
          </h1>
          <MeetingTypeBadge meetingType={meeting.meeting_type} />
        </div>
        <div className="flex gap-4 mt-2 text-sm text-slate-600">
          {meeting.presiding_officer && <span>Presiding: {meeting.presiding_officer}</span>}
          {meeting.call_to_order_time && <span>Called to order: {meeting.call_to_order_time}</span>}
        </div>
      </div>

      {/* Quick Stats */}
      {(() => {
        const totalItems = meeting.agenda_items.length
        const consentItems = meeting.agenda_items.filter(i => i.is_consent_calendar).length
        const substantiveItems = totalItems - consentItems - meeting.agenda_items.filter(i => i.category === 'procedural').length
        const totalVotes = meeting.agenda_items.reduce((sum, i) => sum + i.motions.reduce((s, m) => s + m.votes.length, 0), 0)

        return (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
            <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
              <p className="text-2xl font-bold text-civic-navy">{substantiveItems}</p>
              <p className="text-xs text-slate-500 mt-1">Substantive Items</p>
            </div>
            <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
              <p className="text-2xl font-bold text-civic-navy">{consentItems}</p>
              <p className="text-xs text-slate-500 mt-1">Consent Calendar</p>
            </div>
            <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
              <p className="text-2xl font-bold text-civic-navy">{totalVotes}</p>
              <p className="text-xs text-slate-500 mt-1">Votes Recorded</p>
            </div>
            <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
              <p className="text-2xl font-bold text-civic-navy">{meeting.total_public_comments}</p>
              <p className="text-xs text-slate-500 mt-1">Public Comments</p>
            </div>
          </div>
        )
      })()}

      {/* Conflict Flag Callout — operator only until scanner is validated for public */}
      <OperatorGate>
        {publishedFlags.length > 0 && (
          <div className="bg-civic-amber/10 border border-civic-amber/30 rounded-lg p-4 mb-6">
            <h3 className="font-semibold text-civic-amber">
              {publishedFlags.length} Campaign Contribution {publishedFlags.length !== 1 ? 'Records' : 'Record'} Identified
            </h3>
            <p className="text-sm text-slate-700 mt-1">
              The scanner found overlaps between agenda items, campaign contributions, and financial disclosures.
              A campaign contribution does not imply wrongdoing.
            </p>
          </div>
        )}
      </OperatorGate>

      {/* Attendance */}
      <div className="mb-6">
        <AttendanceRoster attendance={meeting.attendance} />
      </div>

      {/* Hero Item + Local Issue Filter + Topic Board */}
      <MeetingDetailClient
        items={meeting.agenda_items}
        flags={publishedFlags}
      />
    </div>
  )
}
