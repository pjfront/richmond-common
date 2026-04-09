import Link from 'next/link'
import CategoryBadge from './CategoryBadge'

interface MeetingCardProps {
  id: string
  meetingDate: string
  meetingType: string
  presidingOfficer: string | null
  agendaItemCount: number | null
  voteCount: number
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
  voteCount,
  topCategories,
}: MeetingCardProps) {
  return (
    <Link
      href={`/meetings/${id}`}
      className="block bg-white rounded-lg border border-slate-200 p-5 hover:border-civic-navy-light hover:shadow-md transition-all"
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
      <div className="flex gap-4 mt-3 text-sm text-slate-600">
        {agendaItemCount != null && agendaItemCount > 0 && (
          <>
            <span>{agendaItemCount} agenda items</span>
            <span className="text-slate-300">|</span>
          </>
        )}
        <span>{voteCount} votes recorded</span>
      </div>
      {topCategories && topCategories.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {topCategories.map((tc) => (
            <span key={tc.category} className="flex items-center gap-1">
              <CategoryBadge category={tc.category} />
              <span className="text-xs text-slate-400">{tc.count}</span>
            </span>
          ))}
        </div>
      )}
    </Link>
  )
}
