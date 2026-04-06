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
      title: `${title} | Richmond Commons`,
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
      {/* Header — back link + prev/next on one row */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-4">
          <Link href={`/meetings?month=${meeting.meeting_date.substring(0, 7)}`} className="text-sm font-medium text-civic-navy hover:text-civic-navy-light">
            &larr; All Meetings
          </Link>
          <MeetingNav previous={adjacentMeetings.previous} next={adjacentMeetings.next} />
        </div>
        <div className="flex items-center gap-3">
          <h1 className="text-4xl font-bold text-civic-navy">
            {formatDate(meeting.meeting_date)}
          </h1>
          {meeting.meeting_type.toLowerCase() !== 'regular' && (
            <MeetingTypeBadge meetingType={meeting.meeting_type} />
          )}
        </div>
        {/* Metadata line — stats as context, not headlines (D6) */}
        {(() => {
          const totalItems = meeting.agenda_items.length
          const consentItems = meeting.agenda_items.filter(i => i.is_consent_calendar).length
          const substantiveItems = totalItems - consentItems - meeting.agenda_items.filter(i => i.category === 'procedural').length
          const totalVotes = meeting.agenda_items.reduce((sum, i) => sum + i.motions.filter(m => m.votes.length > 0).length, 0)
          const totalMotions = meeting.agenda_items.reduce((sum, i) => sum + i.motions.length, 0)
          const minutesExtracted = totalMotions > 0
          const transcriptComments = meeting.agenda_items.reduce((sum, i) => sum + i.public_comment_count, 0)
          const totalComments = transcriptComments > 0 ? transcriptComments : meeting.total_public_comments

          const parts: string[] = []
          if (meeting.presiding_officer) parts.push(`Presiding: ${meeting.presiding_officer}`)
          if (meeting.call_to_order_time) parts.push(`Called to order: ${meeting.call_to_order_time}`)
          parts.push(`${substantiveItems} items`)
          if (minutesExtracted || totalVotes > 0) parts.push(`${totalVotes} votes`)
          if (totalComments > 0) parts.push(`${totalComments} public comments`)

          return (
            <p className="text-sm text-slate-500 mt-2">
              {parts.join(' · ')}
              {(meeting.agenda_url || meeting.minutes_url) && !meeting.meeting_summary && (
                <>
                  {' · '}
                  <span className="text-civic-navy-light">
                    View official:{' '}
                    {meeting.minutes_url && (
                      <a
                        href={meeting.minutes_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:text-civic-navy hover:underline"
                      >
                        Minutes
                      </a>
                    )}
                    {meeting.minutes_url && meeting.agenda_url && (
                      <span className="text-slate-400"> | </span>
                    )}
                    {meeting.agenda_url && (
                      <a
                        href={meeting.agenda_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:text-civic-navy hover:underline"
                      >
                        Agenda
                      </a>
                    )}
                  </span>
                </>
              )}
            </p>
          )
        })()}
        {meeting.agenda_items.reduce((sum, i) => sum + i.motions.length, 0) === 0 && !meeting.minutes_url && (
          <p className="text-sm text-slate-400 mt-1">
            Minutes not yet published by the City Clerk — vote and comment data typically appear 4–6 weeks after the meeting.
          </p>
        )}
      </div>

      {/* Orientation Preview — forward-looking "what to watch for" */}
      {meeting.orientation_preview && (
        <div className="bg-sky-50/60 rounded-lg border border-sky-200/50 p-5 mb-8">
          <h2 className="text-sm font-medium text-civic-navy uppercase tracking-wide mb-3">
            On the agenda
          </h2>
          <div className="space-y-3 text-sm text-slate-700 leading-relaxed">
            {meeting.orientation_preview.split('\n\n').filter(Boolean).map((para, i) => (
              <p key={i}>
                {para.split(/(\*\*[^*]+\*\*)/).map((chunk, j) =>
                  chunk.startsWith('**') && chunk.endsWith('**')
                    ? <strong key={j} className="font-semibold text-civic-navy">{chunk.slice(2, -2)}</strong>
                    : chunk
                )}
              </p>
            ))}
          </div>
          <p className="text-xs text-slate-400 mt-3">
            AI-generated preview from the published agenda
          </p>
        </div>
      )}

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
          <div className="flex items-center justify-between mt-3">
            <p className="text-xs text-slate-400">
              Auto-generated summary from agenda items and vote records
            </p>
            {(meeting.agenda_url || meeting.minutes_url) && (
              <span className="text-xs text-civic-navy-light">
                View official:{' '}
                {meeting.minutes_url && (
                  <a
                    href={meeting.minutes_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:text-civic-navy hover:underline"
                  >
                    Minutes
                  </a>
                )}
                {meeting.minutes_url && meeting.agenda_url && (
                  <span className="text-slate-400"> | </span>
                )}
                {meeting.agenda_url && (
                  <a
                    href={meeting.agenda_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:text-civic-navy hover:underline"
                  >
                    Agenda
                  </a>
                )}
              </span>
            )}
          </div>
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
