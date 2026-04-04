import Link from 'next/link'
import { getNextMeeting } from '@/lib/queries'

export default async function UpcomingMeetingBanner() {
  const meeting = await getNextMeeting()
  if (!meeting) return null

  const date = new Date(meeting.meeting_date + 'T00:00:00')
  const now = new Date()
  const daysUntil = Math.ceil(
    (date.getTime() - now.getTime()) / (1000 * 60 * 60 * 24),
  )

  // Only show if within 14 days
  if (daysUntil > 14) return null

  const formattedDate = date.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })

  const urgencyText =
    daysUntil === 0
      ? 'Today'
      : daysUntil === 1
        ? 'Tomorrow'
        : `${formattedDate}`

  return (
    <div className="bg-civic-navy/5 border-b border-civic-navy/10">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-2.5">
        <Link
          href={`/meetings/${meeting.id}`}
          className="flex items-center justify-center gap-2 text-sm text-civic-navy hover:text-civic-navy-light transition-colors group"
        >
          <span className="font-medium">
            Next City Council meeting: {urgencyText}
          </span>
          <span className="text-civic-amber text-xs">
            {daysUntil === 0
              ? 'happening now'
              : daysUntil === 1
                ? 'tomorrow'
                : `in ${daysUntil} days`}
          </span>
          <span className="text-slate-400 group-hover:text-civic-navy transition-colors">
            →
          </span>
        </Link>
      </div>
    </div>
  )
}
