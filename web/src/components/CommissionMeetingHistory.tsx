'use client'

import { useState } from 'react'
import MeetingCard from './MeetingCard'
import type { MeetingWithCounts } from '@/lib/types'

interface CommissionMeetingHistoryProps {
  meetings: MeetingWithCounts[]
}

export default function CommissionMeetingHistory({ meetings }: CommissionMeetingHistoryProps) {
  const [showAll, setShowAll] = useState(false)
  const INITIAL_COUNT = 5

  if (meetings.length === 0) {
    return (
      <div className="text-sm text-slate-500 italic">
        No meeting records available yet. Commission meeting minutes are being added.
      </div>
    )
  }

  const visible = showAll ? meetings : meetings.slice(0, INITIAL_COUNT)
  const hasMore = meetings.length > INITIAL_COUNT

  return (
    <div>
      <div className="flex items-baseline gap-3 mb-1">
        <span className="text-sm text-slate-500">
          {meetings.length} meeting{meetings.length !== 1 ? 's' : ''} on record
        </span>
      </div>
      <div className="space-y-3 mt-3">
        {visible.map((m) => (
          <MeetingCard
            key={m.id}
            id={m.id}
            meetingDate={m.meeting_date}
            meetingType={m.meeting_type}
            presidingOfficer={m.presiding_officer}
            agendaItemCount={m.agenda_item_count}
            voteCount={m.vote_count}
            topCategories={m.top_categories}
          />
        ))}
      </div>
      {hasMore && !showAll && (
        <button
          onClick={() => setShowAll(true)}
          className="mt-3 text-sm text-civic-navy hover:text-civic-navy-light font-medium"
        >
          Show all {meetings.length} meetings
        </button>
      )}
      {showAll && hasMore && (
        <button
          onClick={() => setShowAll(false)}
          className="mt-3 text-sm text-civic-navy hover:text-civic-navy-light font-medium"
        >
          Show fewer
        </button>
      )}
    </div>
  )
}
