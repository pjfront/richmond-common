import Link from 'next/link'
import { formatCategory } from './CategoryBadge'
import TopicLabel from './TopicLabel'

interface MeetingCardProps {
  id: string
  meetingDate: string
  meetingType: string
  presidingOfficer: string | null
  agendaItemCount: number
  topCategories?: { category: string; count: number }[]
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

function meetingTypeBadge(type: string) {
  const styles: Record<string, string> = {
    regular: 'bg-civic-navy text-white',
    special: 'bg-civic-amber text-white',
    closed_session: 'bg-slate-600 text-white',
    joint: 'bg-purple-600 text-white',
  }
  const labels: Record<string, string> = {
    regular: 'Regular',
    special: 'Special',
    closed_session: 'Closed Session',
    joint: 'Joint',
  }
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded ${styles[type] ?? 'bg-slate-200 text-slate-700'}`}>
      {labels[type] ?? type}
    </span>
  )
}

export default function MeetingCard({
  id,
  meetingDate,
  meetingType,
  presidingOfficer,
  agendaItemCount,
  topCategories,
}: MeetingCardProps) {
  return (
    <Link
      href={`/meetings/${id}`}
      className="block bg-white rounded-lg border border-slate-200 p-5 hover:border-civic-navy-light hover:shadow-md transition-shadow motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-civic-navy"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-semibold text-lg text-slate-900">
            {formatDate(meetingDate)}
          </h3>
          {presidingOfficer && (
            <p className="text-sm text-slate-500 mt-1">
              Presiding: {presidingOfficer}
            </p>
          )}
        </div>
        {meetingTypeBadge(meetingType)}
      </div>
      <p className="mt-3 text-sm text-slate-600">
        {agendaItemCount > 0
          ? `${agendaItemCount} agenda ${agendaItemCount === 1 ? 'entry' : 'entries'} in this archive`
          : 'No agenda entries in this archive'}
      </p>
      {topCategories && topCategories.length > 0 && (
        <div className="mt-2">
          <p className="text-xs text-slate-500 mb-1.5">Topics assigned by AI</p>
          <div className="flex flex-wrap gap-1.5">
            {topCategories.map((tc) => (
              <span key={tc.category} className="flex items-center gap-1">
                <TopicLabel label={formatCategory(tc.category)} />
                <span className="text-xs text-slate-500">{tc.count}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </Link>
  )
}
