'use client'

import { useState, useMemo, useCallback } from 'react'
import type { MeetingWithCounts, CategoryCount } from '@/lib/types'
import DateFilterBar from './DateFilterBar'
import TopicOverview from './TopicOverview'
import MeetingCard from './MeetingCard'

interface MeetingsPageClientProps {
  meetings: MeetingWithCounts[]
}

function getYearRange() {
  const year = new Date().getFullYear()
  return { start: `${year}-01-01`, end: `${year}-12-31` }
}

export default function MeetingsPageClient({ meetings }: MeetingsPageClientProps) {
  const defaultRange = getYearRange()
  const [dateRange, setDateRange] = useState(defaultRange)

  const handleDateChange = useCallback((range: { start: string; end: string }) => {
    setDateRange(range)
  }, [])

  // Filter meetings by date range
  const filteredMeetings = useMemo(
    () =>
      meetings.filter((m) => m.meeting_date >= dateRange.start && m.meeting_date <= dateRange.end),
    [meetings, dateRange]
  )

  // Aggregate categories across filtered meetings
  const aggregatedCategories = useMemo(() => {
    const catMap = new Map<string, number>()
    for (const m of filteredMeetings) {
      for (const c of m.all_categories) {
        catMap.set(c.category, (catMap.get(c.category) ?? 0) + c.count)
      }
    }
    return Array.from(catMap.entries())
      .map(([category, count]): CategoryCount => ({ category, count }))
      .sort((a, b) => b.count - a.count)
  }, [filteredMeetings])

  // Group filtered meetings by year
  const byYear = useMemo(() => {
    const map = new Map<number, MeetingWithCounts[]>()
    for (const m of filteredMeetings) {
      const year = new Date(m.meeting_date + 'T00:00:00').getFullYear()
      const arr = map.get(year) ?? []
      arr.push(m)
      map.set(year, arr)
    }
    return map
  }, [filteredMeetings])

  const years = useMemo(
    () => Array.from(byYear.keys()).sort((a, b) => b - a),
    [byYear]
  )

  return (
    <>
      <DateFilterBar
        onChange={handleDateChange}
        defaultStart={defaultRange.start}
        defaultEnd={defaultRange.end}
      />

      <TopicOverview categories={aggregatedCategories} />

      {filteredMeetings.length === 0 ? (
        <p className="text-slate-500 mt-8">No meetings in this date range.</p>
      ) : (
        years.map((year) => (
          <section key={year} className="mt-8">
            <h2 className="text-xl font-semibold text-slate-800 mb-4">{year}</h2>
            <div className="space-y-3">
              {(byYear.get(year) ?? []).map((m) => (
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
          </section>
        ))
      )}
    </>
  )
}
