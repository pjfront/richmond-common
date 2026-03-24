import Link from 'next/link'
import MeetingTypeBadge from './MeetingTypeBadge'
import { topicLabelColor } from '@/lib/topic-label-colors'
import type { MeetingWithCounts } from '@/lib/types'

interface NextMeetingCardProps {
  meeting: MeetingWithCounts
  /** Number of published conflict flags for this meeting */
  flagCount?: number
}

function formatRelativeDate(dateStr: string): string {
  const meeting = new Date(dateStr + 'T00:00:00')
  const today = new Date()
  today.setHours(0, 0, 0, 0)

  const diffMs = meeting.getTime() - today.getTime()
  const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24))

  if (diffDays === 0) return 'Today'
  if (diffDays === 1) return 'Tomorrow'
  if (diffDays < 7) return `In ${diffDays} days`

  return meeting.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })
}

function formatFullDate(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

/**
 * NextMeetingCard (S14-B1)
 *
 * Persistent hero card answering "When is the next meeting?"
 * Only renders when a future meeting exists.
 */
export default function NextMeetingCard({ meeting, flagCount = 0 }: NextMeetingCardProps) {
  const relDate = formatRelativeDate(meeting.meeting_date)
  const fullDate = formatFullDate(meeting.meeting_date)
  const topLabels = meeting.top_topic_labels?.slice(0, 4) ?? []

  return (
    <Link
      href={`/meetings/${meeting.id}`}
      className="block bg-white rounded-lg border-2 border-civic-navy/20 p-5 sm:p-6 hover:border-civic-navy/40 hover:shadow-md transition-all mb-8"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <p className="text-sm font-medium text-civic-navy uppercase tracking-wide">
            Next Meeting
          </p>
          <h2 className="text-2xl font-bold text-slate-900">{relDate}</h2>
          <p className="text-sm text-slate-500">{fullDate}</p>
        </div>
        <MeetingTypeBadge meetingType={meeting.meeting_type} />
      </div>

      <div className="flex flex-wrap gap-x-5 gap-y-1 mt-4 text-sm text-slate-600">
        <span>{meeting.agenda_item_count} agenda items</span>
        {meeting.vote_count > 0 && <span>{meeting.vote_count} votes</span>}
        {flagCount > 0 && (
          <span className="text-civic-amber">
            {flagCount} contribution {flagCount === 1 ? 'record' : 'records'}
          </span>
        )}
      </div>

      {topLabels.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-3">
          {topLabels.map((t) => (
            <span
              key={t.label}
              className={`inline-block text-xs font-medium px-2 py-0.5 rounded ${topicLabelColor(t.label)}`}
            >
              {t.label}
            </span>
          ))}
        </div>
      )}
    </Link>
  )
}
