'use client'

import { useMemo } from 'react'
import Link from 'next/link'
import { format, parseISO } from 'date-fns'
import MeetingListCard from './MeetingListCard'
import MeetingTypeBadge from './MeetingTypeBadge'
import type { MeetingWithCounts } from '@/lib/types'

interface MeetingAgendaListProps {
  meetings: MeetingWithCounts[]
  /** Record of meeting_id → published flag count */
  flagCounts?: Record<string, number>
  /** Currently active month key (YYYY-MM) for controlled expansion */
  activeMonth?: string
  /** Compact mode for sidebar use alongside calendar grid */
  compact?: boolean
}

interface MonthGroup {
  key: string        // "2026-03"
  label: string      // "March 2026"
  meetings: MeetingWithCounts[]
}

function groupByMonth(meetings: MeetingWithCounts[]): MonthGroup[] {
  const map = new Map<string, MeetingWithCounts[]>()

  for (const m of meetings) {
    const date = parseISO(m.meeting_date)
    const key = format(date, 'yyyy-MM')
    const arr = map.get(key) ?? []
    arr.push(m)
    map.set(key, arr)
  }

  return Array.from(map.entries())
    .sort(([a], [b]) => b.localeCompare(a)) // most recent first
    .map(([key, meetings]) => ({
      key,
      label: format(parseISO(key + '-01'), 'MMMM yyyy'),
      meetings,
    }))
}

/**
 * MeetingAgendaList (S14-B2)
 *
 * Month-grouped accordion list of meetings. Primary default view.
 * Most recent month expanded by default. Uses native <details> for
 * accessible, zero-JS expand/collapse.
 *
 * Dense list design: no empty-state rows, just months with meetings.
 * Richmond averages ~2 meetings/month — this layout works much better
 * than a sparse calendar grid at low meeting density.
 */
export default function MeetingAgendaList({
  meetings,
  flagCounts,
  activeMonth,
  compact = false,
}: MeetingAgendaListProps) {
  const monthGroups = useMemo(() => groupByMonth(meetings), [meetings])

  if (monthGroups.length === 0) {
    return (
      <p className="text-slate-500 py-8">No meetings found.</p>
    )
  }

  // Default: open the current + previous month (first two in sorted order)
  // If a specific month is selected via URL, open only that one
  const openMonths = useMemo(() => {
    if (activeMonth) return new Set([activeMonth])
    const keys = new Set<string>()
    if (monthGroups[0]) keys.add(monthGroups[0].key)
    if (monthGroups[1]) keys.add(monthGroups[1].key)
    return keys
  }, [activeMonth, monthGroups])

  if (compact) {
    return (
      <div className="space-y-4 max-h-[calc(100vh-8rem)] overflow-y-auto pr-1">
        <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">
          All meetings
        </h3>
        {monthGroups.map((group) => (
          <div key={group.key}>
            <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-1.5">
              {group.label}
            </h4>
            <div className="space-y-1">
              {group.meetings.map((m) => {
                const date = parseISO(m.meeting_date)
                return (
                  <Link
                    key={m.id}
                    href={`/meetings/${m.id}`}
                    className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-slate-50 transition-colors group"
                  >
                    <span className="text-xs text-slate-500 w-12 shrink-0">
                      {format(date, 'MMM d')}
                    </span>
                    <MeetingTypeBadge meetingType={m.meeting_type} compact />
                    <span className="text-xs text-slate-400 ml-auto shrink-0">
                      {m.agenda_item_count} items
                    </span>
                  </Link>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {monthGroups.map((group) => {
        const totalItems = group.meetings.reduce((s, m) => s + m.agenda_item_count, 0)

        return (
          <details
            key={group.key}
            open={openMonths.has(group.key)}
            className="group"
          >
            <summary className="flex items-center justify-between cursor-pointer select-none rounded-lg bg-slate-50 border border-slate-200 px-4 py-3 hover:bg-slate-100 transition-colors list-none">
              <div className="flex items-center gap-3">
                {/* Chevron rotates when open */}
                <svg
                  className="w-4 h-4 text-slate-400 transition-transform group-open:rotate-90"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
                <h2 className="text-lg font-semibold text-slate-800">
                  {group.label}
                </h2>
              </div>
              <span className="text-sm text-slate-500">
                {group.meetings.length} {group.meetings.length === 1 ? 'meeting' : 'meetings'}
                {' '}&middot;{' '}
                {totalItems} items
              </span>
            </summary>

            <div className="space-y-2 mt-2 pl-2">
              {group.meetings.map((m) => (
                <MeetingListCard
                  key={m.id}
                  meeting={m}
                  flagCount={flagCounts?.[m.id] ?? 0}
                />
              ))}
            </div>
          </details>
        )
      })}
    </div>
  )
}
