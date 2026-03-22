'use client'

import { useMemo, useCallback, useState } from 'react'
import { useQueryState, parseAsString } from 'nuqs'
import { format } from 'date-fns'
import NextMeetingCard from './NextMeetingCard'
import MeetingAgendaList from './MeetingAgendaList'
import MiniCalendar from './MiniCalendar'
import CalendarGrid from './CalendarGrid'
import type { MeetingWithCounts } from '@/lib/types'

type ViewMode = 'list' | 'calendar'

interface MeetingsDiscoveryProps {
  meetings: MeetingWithCounts[]
  /** Record of meeting_id → published flag count (serializable across server/client boundary) */
  flagCounts: Record<string, number>
}

/**
 * MeetingsDiscovery (S14-B)
 *
 * Client-side wrapper for the meetings index page.
 * Manages URL state (?month=2026-03), view toggle, and orchestrates
 * NextMeetingCard + MeetingAgendaList/CalendarGrid + MiniCalendar.
 *
 * Replaces MeetingsPageClient.
 */
export default function MeetingsDiscovery({ meetings, flagCounts }: MeetingsDiscoveryProps) {
  const [month, setMonth] = useQueryState('month', parseAsString)
  const [viewMode, setViewMode] = useState<ViewMode>('list')

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

      {/* View toggle */}
      <div className="flex items-center justify-end gap-1 mb-4">
        <span className="text-xs text-slate-400 mr-2">View</span>
        <button
          onClick={() => setViewMode('list')}
          className={`p-1.5 rounded ${viewMode === 'list' ? 'bg-civic-navy text-white' : 'text-slate-400 hover:text-slate-600 hover:bg-slate-100'}`}
          aria-label="List view"
          title="List view"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
        <button
          onClick={() => setViewMode('calendar')}
          className={`p-1.5 rounded ${viewMode === 'calendar' ? 'bg-civic-navy text-white' : 'text-slate-400 hover:text-slate-600 hover:bg-slate-100'}`}
          aria-label="Calendar view"
          title="Calendar view"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        </button>
      </div>

      {viewMode === 'list' ? (
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
      ) : (
        <CalendarGrid meetings={meetings} />
      )}
    </>
  )
}
