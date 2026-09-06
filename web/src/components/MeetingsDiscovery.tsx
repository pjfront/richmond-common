'use client'

import { useCallback } from 'react'
import { useQueryState, parseAsString } from 'nuqs'
import MeetingAgendaList from './MeetingAgendaList'
import MiniCalendar from './MiniCalendar'
import type { MeetingWithCounts } from '@/lib/types'

interface MeetingsDiscoveryProps {
  meetings: MeetingWithCounts[]
}

/**
 * MeetingsDiscovery (S14-B)
 *
 * Client-side wrapper for the meetings index page.
 * Manages URL state (?month=2026-03) and orchestrates
 * MeetingAgendaList + MiniCalendar sidebar.
 *
 * Calendar grid view removed — list is the only view needed
 * for ~2 meetings/month density. Mini-calendar sidebar handles
 * temporal navigation.
 */
export default function MeetingsDiscovery({ meetings }: MeetingsDiscoveryProps) {
  const [month, setMonth] = useQueryState('month', parseAsString)

  // When mini-calendar clicks a meeting, navigate to its month
  const handleCalendarDateClick = useCallback((meetingId: string) => {
    const meeting = meetings.find((m) => m.id === meetingId)
    if (meeting) {
      const monthKey = meeting.meeting_date.substring(0, 7) // "YYYY-MM"
      setMonth(monthKey)
    }
  }, [meetings, setMonth])

  // If a month is selected via URL, default-open that month in the list
  const activeMonth = month ?? undefined

  return (
    <div className="flex gap-6">
      {/* Main agenda list */}
      <div className="flex-1 min-w-0">
        <MeetingAgendaList
          meetings={meetings}
          activeMonth={activeMonth}
        />
      </div>

      {/* Mini-calendar sidebar — desktop only */}
      <aside className="hidden lg:block w-56 shrink-0">
        <div className="sticky top-24">
          <MiniCalendar
            meetings={meetings}
            onDateClick={handleCalendarDateClick}
          />
        </div>
      </aside>
    </div>
  )
}
