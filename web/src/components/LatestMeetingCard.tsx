import Link from 'next/link'
import type { Meeting } from '@/lib/types'

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
  return (
    <Link
      href={`/meetings/${meeting.id}`}
      className="block bg-white rounded-lg border border-slate-200 p-6 hover:border-civic-navy-light hover:shadow-sm transition-all"
    >
      <p className="text-xs font-medium text-civic-navy-light uppercase tracking-wide mb-1">
        Latest Meeting
      </p>
      <h3 className="text-xl font-bold text-slate-900">{formatDate(meeting.meeting_date)}</h3>
      <p className="text-sm text-slate-500 capitalize mt-1">{meeting.meeting_type} Meeting</p>
      <div className="flex gap-6 mt-4 text-sm text-slate-600">
        <span>{agendaItemCount} agenda items</span>
        <span>{voteCount} votes recorded</span>
        {flagCount > 0 && (
          <span className="text-civic-amber font-medium">
            {flagCount} transparency flag{flagCount !== 1 ? 's' : ''}
          </span>
        )}
      </div>
    </Link>
  )
}
