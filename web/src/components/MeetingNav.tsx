import Link from 'next/link'
import type { AdjacentMeeting } from '@/lib/queries'

function formatShortDate(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

export default function MeetingNav({
  previous,
  next,
}: {
  previous: AdjacentMeeting | null
  next: AdjacentMeeting | null
}) {
  if (!previous && !next) return null

  return (
    <nav aria-label="Meeting navigation" className="flex items-center justify-between gap-4">
      <div className="flex-1">
        {previous && (
          <Link
            href={`/meetings/${previous.id}`}
            className="group inline-flex items-center gap-2 text-sm text-civic-navy-light hover:text-civic-navy transition-colors"
          >
            <span aria-hidden="true">&larr;</span>
            <span>
              <span className="text-slate-500 group-hover:text-civic-navy-light">Previous</span>
              <br />
              <span className="font-medium">{formatShortDate(previous.meeting_date)}</span>
            </span>
          </Link>
        )}
      </div>
      <div className="flex-1 text-right">
        {next && (
          <Link
            href={`/meetings/${next.id}`}
            className="group inline-flex items-center gap-2 text-sm text-civic-navy-light hover:text-civic-navy transition-colors justify-end"
          >
            <span>
              <span className="text-slate-500 group-hover:text-civic-navy-light">Next</span>
              <br />
              <span className="font-medium">{formatShortDate(next.meeting_date)}</span>
            </span>
            <span aria-hidden="true">&rarr;</span>
          </Link>
        )}
      </div>
    </nav>
  )
}
