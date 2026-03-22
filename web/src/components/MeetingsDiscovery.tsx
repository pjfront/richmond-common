'use client'

import { useMemo, useCallback } from 'react'
import { useQueryState, parseAsString } from 'nuqs'
import { format } from 'date-fns'
import NextMeetingCard from './NextMeetingCard'
import MeetingAgendaList from './MeetingAgendaList'
import MiniCalendar from './MiniCalendar'
import type { MeetingWithCounts } from '@/lib/types'

interface MeetingsDiscoveryProps {
  meetings: MeetingWithCounts[]
  /** Record of meeting_id → published flag count (serializable across server/client boundary) */
  flagCounts: Record<string, number>
}

/**
 * MeetingsDiscovery (S14-B)
 *
 * Client-side wrapper for the meetings index page.
 * Manages URL state (?month=2026-03) and orchestrates
 * NextMeetingCard + MeetingAgendaList + MiniCalendar.
 *
 * Replaces MeetingsPageClient.
 */
export default function MeetingsDiscovery({ meetings, flagCounts }: MeetingsDiscoveryProps) {
  const [month, setMonth] = useQueryState('month', parseAsString)

  // Find the next upcoming meeting (future or today)
  const nextMeeting = useMemo(() => {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const todayStr = format(today, 'yyyy-MM-dd')

    // meetings are sorted DESC, so find the last one >= today
    const future = meetings.filter((m) => m.meeting_date >= todayStr)
    return future.length > 0 ? future[future.length - 1] : null
  }, [meetings])

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

  // Next meeting flag count
  const nextMeetingFlags = nextMeeting ? flagCounts[nextMeeting.id] ?? 0 : 0

  return (
    <>
      {nextMeeting && (
        <NextMeetingCard
          meeting={nextMeeting}
          flagCount={nextMeetingFlags}
        />
      )}

      <div className="flex gap-6">
        {/* Main agenda list */}
        <div className="flex-1 min-w-0">
          <MeetingAgendaList
            meetings={meetings}
            flagCounts={flagCounts}
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
    </>
  )
}
