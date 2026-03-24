'use client'

import { useMemo } from 'react'
import Link from 'next/link'
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
  isToday,
  parseISO,
} from 'date-fns'
import MeetingTypeBadge from './MeetingTypeBadge'
import { topicLabelColor } from '@/lib/topic-label-colors'
import type { MeetingWithCounts } from '@/lib/types'

interface CalendarGridProps {
  meetings: MeetingWithCounts[]
  /** Currently displayed month as "YYYY-MM" string, or null for current month */
  month: string | null
  /** Callback when user navigates months */
  onMonthChange: (month: string) => void
}

const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

/**
 * CalendarGrid (S14-B5)
 *
 * Full monthly grid available as opt-in alternative to the default
 * month-grouped agenda list. Each day cell shows meeting badge + item count.
 * Research B found grids underperform at low meeting density (~2/month),
 * so this is the secondary view, not the default.
 */
export default function CalendarGrid({ meetings, month, onMonthChange }: CalendarGridProps) {
  const currentMonth = month ? parseISO(month + '-01') : new Date()

  // Map date string → meetings for quick lookup
  const meetingsByDate = useMemo(() => {
    const map = new Map<string, MeetingWithCounts[]>()
    for (const m of meetings) {
      const arr = map.get(m.meeting_date) ?? []
      arr.push(m)
      map.set(m.meeting_date, arr)
    }
    return map
  }, [meetings])

  // Generate calendar grid days
  const calendarDays = useMemo(() => {
    const monthStart = startOfMonth(currentMonth)
    const monthEnd = endOfMonth(currentMonth)
    const gridStart = startOfWeek(monthStart)
    const gridEnd = endOfWeek(monthEnd)
    return eachDayOfInterval({ start: gridStart, end: gridEnd })
  }, [currentMonth])

  return (
    <div>
      {/* Month navigation */}
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={() => onMonthChange(format(subMonths(currentMonth, 1), 'yyyy-MM'))}
          className="p-2 hover:bg-slate-100 rounded text-slate-500 hover:text-slate-700"
          aria-label="Previous month"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <h2 className="text-xl font-semibold text-slate-800">
          {format(currentMonth, 'MMMM yyyy')}
        </h2>
        <button
          onClick={() => onMonthChange(format(addMonths(currentMonth, 1), 'yyyy-MM'))}
          className="p-2 hover:bg-slate-100 rounded text-slate-500 hover:text-slate-700"
          aria-label="Next month"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>

      {/* Weekday headers */}
      <div className="grid grid-cols-7 border-b border-slate-200 mb-1">
        {WEEKDAYS.map((d) => (
          <div key={d} className="text-center text-xs font-medium text-slate-500 py-2">
            <span className="hidden sm:inline">{d}</span>
            <span className="sm:hidden">{d.substring(0, 3)}</span>
          </div>
        ))}
      </div>

      {/* Day grid */}
      <div className="grid grid-cols-7 border-l border-t border-slate-200">
        {calendarDays.map((day) => {
          const dateStr = format(day, 'yyyy-MM-dd')
          const dayMeetings = meetingsByDate.get(dateStr) ?? []
          const inMonth = isSameMonth(day, currentMonth)
          const today = isToday(day)

          const baseClasses = `
            min-h-[80px] sm:min-h-[100px] border-r border-b border-slate-200 p-1
            ${inMonth ? 'bg-white' : 'bg-slate-50'}
            ${today ? 'ring-2 ring-inset ring-civic-navy/20' : ''}
          `

          // Single meeting: entire cell is clickable
          if (dayMeetings.length === 1) {
            const m = dayMeetings[0]
            return (
              <Link
                key={dateStr}
                href={`/meetings/${m.id}`}
                className={`${baseClasses} block hover:bg-civic-navy/5 transition-colors cursor-pointer`}
              >
                <div className={`text-xs mb-1 ${inMonth ? 'text-slate-600' : 'text-slate-300'}`}>
                  {format(day, 'd')}
                </div>
                <MeetingTypeBadge meetingType={m.meeting_type} compact />
                <div className="text-xs text-slate-500 mt-0.5">
                  {m.agenda_item_count} items
                </div>
                {m.top_topic_labels && m.top_topic_labels.length > 0 && (
                  <div className="hidden sm:flex flex-wrap gap-0.5 mt-1">
                    {m.top_topic_labels.slice(0, 3).map((t) => (
                      <span key={t.label} className={`text-[10px] leading-tight px-1 rounded ${topicLabelColor(t.label)}`}>
                        {t.label}
                      </span>
                    ))}
                  </div>
                )}
              </Link>
            )
          }

          // Zero or multiple meetings: individual links per meeting
          return (
            <div
              key={dateStr}
              className={baseClasses}
            >
              <div className={`text-xs mb-1 ${inMonth ? 'text-slate-600' : 'text-slate-300'}`}>
                {format(day, 'd')}
              </div>
              {dayMeetings.map((m) => (
                <Link
                  key={m.id}
                  href={`/meetings/${m.id}`}
                  className="block rounded p-1 hover:bg-slate-50 transition-colors mb-0.5"
                >
                  <MeetingTypeBadge meetingType={m.meeting_type} compact />
                  <div className="text-xs text-slate-500 mt-0.5">
                    {m.agenda_item_count} items
                  </div>
                  {m.top_topic_labels && m.top_topic_labels.length > 0 && (
                    <div className="hidden sm:flex flex-wrap gap-0.5 mt-1">
                      {m.top_topic_labels.slice(0, 2).map((t) => (
                        <span key={t.label} className="text-[10px] text-slate-500 leading-tight">
                          {t.label}
                        </span>
                      ))}
                    </div>
                  )}
                </Link>
              ))}
            </div>
          )
        })}
      </div>
    </div>
  )
}
