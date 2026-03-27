import { notFound } from 'next/navigation'
import Link from 'next/link'
import type { Metadata } from 'next'
import { getMeeting, getConflictFlags, getAdjacentMeetings } from '@/lib/queries'
import { CONFIDENCE_PUBLISHED } from '@/lib/thresholds'
import AttendanceRoster from '@/components/AttendanceRoster'
import MeetingTypeBadge from '@/components/MeetingTypeBadge'
import MeetingDetailClient from '@/components/MeetingDetailClient'
import RecordVisit from '@/components/RecordVisit'
import OperatorGate from '@/components/OperatorGate'
import MeetingNav from '@/components/MeetingNav'

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
  const title = `${formatDate(meeting.meeting_date)} Meeting`
  const description = `Richmond City Council ${meeting.meeting_type} meeting on ${formatDate(meeting.meeting_date)}. Agenda items, votes, and plain English summaries.`
  return {
    title,
    description,
    openGraph: {
      title: `${title} | Richmond Common`,
      description,
      type: 'article',
    },
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

  const [flags, adjacentMeetings] = await Promise.all([
    getConflictFlags(id),
    getAdjacentMeetings(meeting.meeting_date, meeting.body_id, meeting.meeting_type),
  ])
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
        <div className="flex items-center justify-between">
          <Link href={`/meetings?month=${meeting.meeting_date.substring(0, 7)}`} className="text-base font-semibold text-civic-navy hover:text-civic-navy-light">
            &larr; All Meetings
          </Link>
        </div>
        <div className="mt-3 mb-4">
          <MeetingNav previous={adjacentMeetings.previous} next={adjacentMeetings.next} />
        </div>
        <div className="flex items-center gap-3 mt-2">
          <h1 className="text-4xl font-bold text-civic-navy">
            {formatDate(meeting.meeting_date)}
          </h1>
          <MeetingTypeBadge meetingType={meeting.meeting_type} />
        </div>
        <div className="flex flex-wrap gap-4 mt-2 text-sm text-slate-600">
          {meeting.presiding_officer && <span>Presiding: {meeting.presiding_officer}</span>}
          {meeting.call_to_order_time && <span>Called to order: {meeting.call_to_order_time}</span>}
          {meeting.agenda_url && (
            <a
              href={meeting.agenda_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-civic-navy-light hover:text-civic-navy hover:underline"
            >
              View official agenda &rarr;
            </a>
          )}
        </div>
      </div>

      {/* Quick Stats */}
      {(() => {
        const totalItems = meeting.agenda_items.length
        const consentItems = meeting.agenda_items.filter(i => i.is_consent_calendar).length
        const substantiveItems = totalItems - consentItems - meeting.agenda_items.filter(i => i.category === 'procedural').length
        const totalVotes = meeting.agenda_items.reduce((sum, i) => sum + i.motions.filter(m => m.votes.length > 0).length, 0)
        const totalMotions = meeting.agenda_items.reduce((sum, i) => sum + i.motions.length, 0)
        // Minutes are "extracted" when motions exist (votes are children of motions).
        // A minutes_url alone just means the PDF was discovered, not parsed.
        const minutesExtracted = totalMotions > 0
        // S20: sum per-item comment counts (Granicus/YouTube-sourced) for meeting total.
        // Fall back to public_comments table total if per-item counts aren't available.
        const transcriptComments = meeting.agenda_items.reduce((sum, i) => sum + i.public_comment_count, 0)
        const totalComments = transcriptComments > 0 ? transcriptComments : meeting.total_public_comments

        return (
          <>
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
              {minutesExtracted || totalVotes > 0 ? (
                <>
                  <p className="text-2xl font-bold text-civic-navy">{totalVotes}</p>
                  <p className="text-xs text-slate-500 mt-1">Votes Recorded</p>
                </>
              ) : (
                <p className="text-sm text-slate-400 mt-2">Pending minutes</p>
              )}
            </div>
            <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
              {totalComments > 0 ? (
                <>
                  <p className="text-2xl font-bold text-civic-navy">{totalComments}</p>
                  <p className="text-xs text-slate-500 mt-1">Public Comments</p>
                </>
              ) : minutesExtracted ? (
                <>
                  <p className="text-2xl font-bold text-civic-navy">0</p>
                  <p className="text-xs text-slate-500 mt-1">Public Comments</p>
                </>
              ) : (
                <p className="text-sm text-slate-400 mt-2">Pending minutes</p>
              )}
            </div>
          </div>
          {!minutesExtracted && totalVotes === 0 && (
            <p className="text-xs text-slate-400 mt-2">
              Vote counts and public comment details are available after the City Clerk publishes official minutes, typically 4-6 weeks after the meeting.
            </p>
          )}
          </>
        )
      })()}

      {/* Meeting Summary — below stats */}
      {meeting.meeting_summary && (
        <div className="bg-amber-50/60 rounded-lg border border-amber-200/50 p-5 mb-8">
          <h2 className="text-sm font-medium text-civic-navy uppercase tracking-wide mb-3">
            What happened
          </h2>
          <ul className="space-y-1.5 text-sm text-slate-700 leading-relaxed list-disc list-outside ml-4">
            {meeting.meeting_summary.split('\n').filter(Boolean).map((bullet, i) => (
              <li key={i}>{bullet.replace(/^[•\-]\s*/, '')}</li>
            ))}
          </ul>
          <p className="text-xs text-slate-400 mt-3">
            Auto-generated summary from agenda items and vote records
          </p>
        </div>
      )}

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

      {/* Bottom meeting navigation */}
      <div className="mt-10 pt-6 border-t border-slate-200">
        <MeetingNav previous={adjacentMeetings.previous} next={adjacentMeetings.next} />
      </div>
    </div>
  )
}
