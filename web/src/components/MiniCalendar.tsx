'use client'

import { useMemo, useState } from 'react'
import {
  startOfMonth,
  endOfMonth,
  startOfWeek,
  endOfWeek,
  eachDayOfInterval,
  format,
  addMonths,
  subMonths,
  isSameMonth,
  isSameDay,
  parseISO,
  isToday,
} from 'date-fns'
import { normalizeMeetingType } from './MeetingTypeBadge'

interface MiniCalendarProps {
  /** All meetings — used to place dots on calendar days */
  meetings: Array<{ meeting_date: string; meeting_type: string; id: string }>
  /** Called when user clicks a meeting date */
  onDateClick?: (meetingId: string) => void
}

/** Meeting type → dot color (matches MeetingTypeBadge color scheme) */
const DOT_COLORS: Record<string, string> = {
  regular: 'bg-blue-500',
  special: 'bg-orange-500',
  closed_session: 'bg-purple-500',
  joint: 'bg-teal-500',
}

const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']

/**
 * MiniCalendar (S14-B3)
 *
 * Compact month grid as secondary navigation aid.
 * Meeting dates show colored dot indicators matching meeting type colors.
 * Desktop: sidebar alongside MeetingAgendaList.
 * Mobile: collapsible.
 */
export default function MiniCalendar({ meetings, onDateClick }: MiniCalendarProps) {
  const [currentMonth, setCurrentMonth] = useState(new Date())

  // Build a map of date string → meeting info for the current month view
  const meetingsByDate = useMemo(() => {
    const map = new Map<string, Array<{ type: string; id: string }>>()
    for (const m of meetings) {
      const dateStr = m.meeting_date // "YYYY-MM-DD"
      const arr = map.get(dateStr) ?? []
      arr.push({ type: normalizeMeetingType(m.meeting_type), id: m.id })
      map.set(dateStr, arr)
    }
    return map
  }, [meetings])

  // Generate calendar grid days (includes days from adjacent months to fill the grid)
  const calendarDays = useMemo(() => {
    const monthStart = startOfMonth(currentMonth)
    const monthEnd = endOfMonth(currentMonth)
    const gridStart = startOfWeek(monthStart)
    const gridEnd = endOfWeek(monthEnd)
    return eachDayOfInterval({ start: gridStart, end: gridEnd })
  }, [currentMonth])

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-3">
      {/* Month navigation */}
      <div className="flex items-center justify-between mb-2">
        <button
          onClick={() => setCurrentMonth((m) => subMonths(m, 1))}
          className="p-1 hover:bg-slate-100 rounded text-slate-500 hover:text-slate-700"
          aria-label="Previous month"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <h3 className="text-sm font-semibold text-slate-700">
          {format(currentMonth, 'MMMM yyyy')}
        </h3>
        <button
          onClick={() => setCurrentMonth((m) => addMonths(m, 1))}
          className="p-1 hover:bg-slate-100 rounded text-slate-500 hover:text-slate-700"
          aria-label="Next month"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>

      {/* Weekday headers */}
      <div className="grid grid-cols-7 gap-0 mb-1">
        {WEEKDAYS.map((d) => (
          <div key={d} className="text-center text-xs text-slate-400 py-1">
            {d}
          </div>
        ))}
      </div>

      {/* Day grid */}
      <div className="grid grid-cols-7 gap-0">
        {calendarDays.map((day) => {
          const dateStr = format(day, 'yyyy-MM-dd')
          const dayMeetings = meetingsByDate.get(dateStr)
          const inMonth = isSameMonth(day, currentMonth)
          const today = isToday(day)

          return (
            <button
              key={dateStr}
              onClick={() => {
                if (dayMeetings && dayMeetings.length > 0 && onDateClick) {
                  onDateClick(dayMeetings[0].id)
                }
              }}
              disabled={!dayMeetings || dayMeetings.length === 0}
              className={`
                relative flex flex-col items-center justify-center p-1 text-xs rounded
                ${inMonth ? 'text-slate-700' : 'text-slate-300'}
                ${today ? 'font-bold ring-1 ring-civic-navy/30' : ''}
                ${dayMeetings ? 'cursor-pointer hover:bg-slate-50' : 'cursor-default'}
              `}
              title={dayMeetings ? `${dayMeetings.length} meeting${dayMeetings.length > 1 ? 's' : ''}` : undefined}
            >
              <span>{format(day, 'd')}</span>
              {/* Meeting dots */}
              {dayMeetings && dayMeetings.length > 0 && (
                <div className="flex gap-0.5 mt-0.5">
                  {dayMeetings.map((dm, i) => (
                    <span
                      key={i}
                      className={`w-1.5 h-1.5 rounded-full ${DOT_COLORS[dm.type] ?? 'bg-slate-400'}`}
                      aria-label={`${dm.type} meeting`}
                    />
                  ))}
                </div>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
