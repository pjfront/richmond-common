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
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)

  const handleDateChange = useCallback((range: { start: string; end: string }) => {
    setDateRange(range)
    setSelectedCategory(null) // Clear category filter when date range changes
  }, [])

  const handleCategoryClick = useCallback((category: string) => {
    setSelectedCategory((prev) => (prev === category ? null : category))
  }, [])

  // Filter meetings by date range
  const dateFilteredMeetings = useMemo(
    () =>
      meetings.filter((m) => m.meeting_date >= dateRange.start && m.meeting_date <= dateRange.end),
    [meetings, dateRange]
  )

  // Further filter by selected category
  const filteredMeetings = useMemo(() => {
    if (!selectedCategory) return dateFilteredMeetings
    return dateFilteredMeetings.filter((m) =>
      m.all_categories.some((c) => c.category === selectedCategory)
    )
  }, [dateFilteredMeetings, selectedCategory])

  // Aggregate categories across date-filtered meetings (not category-filtered,
  // so the overview stays stable when a category is selected)
  const aggregatedCategories = useMemo(() => {
    const catMap = new Map<string, number>()
    for (const m of dateFilteredMeetings) {
      for (const c of m.all_categories) {
        catMap.set(c.category, (catMap.get(c.category) ?? 0) + c.count)
      }
    }
    return Array.from(catMap.entries())
      .map(([category, count]): CategoryCount => ({ category, count }))
      .sort((a, b) => b.count - a.count)
  }, [dateFilteredMeetings])

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

      <TopicOverview
        categories={aggregatedCategories}
        onCategoryClick={handleCategoryClick}
        selectedCategory={selectedCategory}
      />

      {selectedCategory && (
        <div className="flex items-center gap-2 text-sm text-slate-600 mb-4">
          <span>
            Showing <strong>{filteredMeetings.length}</strong> of {dateFilteredMeetings.length} meetings
            with <strong>{selectedCategory.charAt(0).toUpperCase() + selectedCategory.slice(1)}</strong> items
          </span>
          <button
            onClick={() => setSelectedCategory(null)}
            className="text-civic-navy hover:underline"
          >
            clear filter
          </button>
        </div>
      )}

      {filteredMeetings.length === 0 ? (
        <p className="text-slate-500 mt-8">
          {selectedCategory
            ? `No meetings with ${selectedCategory} items in this date range.`
            : 'No meetings in this date range.'}
        </p>
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
