import Link from 'next/link'
import MeetingTypeBadge, { getMeetingTypeBorderAccent } from './MeetingTypeBadge'
import CategoryBadge from './CategoryBadge'
import type { MeetingWithCounts } from '@/lib/types'

interface MeetingListCardProps {
  meeting: MeetingWithCounts
  /** Number of published conflict flags for this meeting */
  flagCount?: number
}

function formatDayDate(dateStr: string): { day: string; monthDay: string } {
  const date = new Date(dateStr + 'T00:00:00')
  return {
    day: date.toLocaleDateString('en-US', { weekday: 'short' }),
    monthDay: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
  }
}

/**
 * MeetingListCard (S14-B2)
 *
 * Richer meeting card for the month-grouped agenda list.
 * Shows date, type badge, item count, top categories, campaign finance indicator.
 * Left border accent encodes meeting type (matches MeetingTypeBadge colors).
 */
export default function MeetingListCard({ meeting, flagCount = 0 }: MeetingListCardProps) {
  const { day, monthDay } = formatDayDate(meeting.meeting_date)
  const borderAccent = getMeetingTypeBorderAccent(meeting.meeting_type)
  const topCats = meeting.top_categories?.slice(0, 3) ?? []

  return (
    <Link
      href={`/meetings/${meeting.id}`}
      className={`block bg-white rounded-lg border border-slate-200 border-l-4 ${borderAccent} p-4 hover:border-slate-300 hover:shadow-sm transition-all`}
    >
      <div className="flex items-start gap-4">
        {/* Date column */}
        <div className="text-center shrink-0 w-14">
          <p className="text-xs text-slate-500 uppercase">{day}</p>
          <p className="text-lg font-bold text-slate-800">{monthDay}</p>
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <MeetingTypeBadge meetingType={meeting.meeting_type} compact />
            {meeting.presiding_officer && (
              <span className="text-xs text-slate-400">
                {meeting.presiding_officer}
              </span>
            )}
          </div>

          <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-1.5 text-sm text-slate-600">
            <span>{meeting.agenda_item_count} items</span>
            {meeting.vote_count > 0 && <span>{meeting.vote_count} votes</span>}
            {flagCount > 0 && (
              <span className="text-civic-amber">
                {flagCount} contribution {flagCount === 1 ? 'record' : 'records'}
              </span>
            )}
          </div>

          {topCats.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {topCats.map((tc) => (
                <CategoryBadge key={tc.category} category={tc.category} />
              ))}
            </div>
          )}
        </div>
      </div>
    </Link>
  )
}
