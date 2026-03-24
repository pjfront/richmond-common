import Link from 'next/link'
import type { Meeting } from '@/lib/types'
import OperatorGate from './OperatorGate'

function formatDate(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

interface LatestMeetingCardProps {
  meeting: Meeting
  agendaItemCount: number
  voteCount: number
  flagCount: number
}

export default function LatestMeetingCard({
  meeting,
  agendaItemCount,
  voteCount,
  flagCount,
}: LatestMeetingCardProps) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const meetingDate = new Date(meeting.meeting_date + 'T00:00:00')
  const isPast = meetingDate < today
  const label = isPast ? 'Latest Meeting' : 'Next Meeting'

  return (
    <Link
      href={`/meetings/${meeting.id}`}
      className="block bg-white rounded-lg border border-slate-200 p-6 hover:border-civic-navy-light hover:shadow-sm transition-all"
    >
      <p className="text-xs font-medium text-civic-navy-light uppercase tracking-wide mb-1">
        {label}
      </p>
      <h3 className="text-xl font-bold text-slate-900">{formatDate(meeting.meeting_date)}</h3>
      <p className="text-sm text-slate-500 capitalize mt-1">{meeting.meeting_type} Meeting</p>
      <div className="flex gap-6 mt-4 text-sm text-slate-600">
        <span>{agendaItemCount} agenda items</span>
        {isPast && voteCount > 0 && <span>{voteCount} votes recorded</span>}
        <OperatorGate>
          {flagCount > 0 && (
            <span className="text-civic-amber font-medium">
              {flagCount} transparency flag{flagCount !== 1 ? 's' : ''}
            </span>
          )}
        </OperatorGate>
      </div>
    </Link>
  )
}
