'use client'

import { useState } from 'react'
import Link from 'next/link'
import * as Collapsible from '@radix-ui/react-collapsible'
import MeetingTypeBadge, { getMeetingTypeBorderAccent } from './MeetingTypeBadge'

import { useOperatorMode } from './OperatorModeProvider'
import TopicLabel from './TopicLabel'
import type { MeetingWithCounts } from '@/lib/types'

interface MeetingListCardProps {
  meeting: MeetingWithCounts
  /** Number of published conflict flags for this meeting */
  flagCount?: number
}

function formatDayDate(dateStr: string): { day: string; monthDay: string } {
  const date = new Date(dateStr + 'T00:00:00')
  return {
    day: date.toLocaleDateString('en-US', { weekday: 'short' }),
    monthDay: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
  }
}

/**
 * MeetingListCard (S14-B4)
 *
 * Meeting card for the month-grouped agenda list.
 * The entire card is a link to the meeting detail page.
 * Chevron toggles an expandable topic/vote preview without navigating.
 * Left border accent encodes meeting type (matches MeetingTypeBadge colors).
 */
export default function MeetingListCard({ meeting, flagCount = 0 }: MeetingListCardProps) {
  const { isOperator } = useOperatorMode()
  const [open, setOpen] = useState(false)
  const { day, monthDay } = formatDayDate(meeting.meeting_date)
  const visibleFlagCount = isOperator ? flagCount : 0
  const borderAccent = getMeetingTypeBorderAccent(meeting.meeting_type)
  const topLabels = meeting.top_topic_labels?.slice(0, 4) ?? []
  const allLabels = meeting.all_topic_labels ?? []
  const hasExpandContent = allLabels.length > 0 || meeting.vote_count > 0 || visibleFlagCount > 0

  return (
    <Collapsible.Root open={open} onOpenChange={setOpen}>
      <div
        className={`bg-white rounded-lg border border-slate-200 border-l-4 ${borderAccent} transition-all ${
          open ? 'shadow-sm border-slate-300' : 'hover:border-slate-300 hover:shadow-sm'
        }`}
      >
        {/* Card face — navigates to meeting detail */}
        <Link
          href={`/meetings/${meeting.id}`}
          className="block px-5 py-4 focus-visible:outline-2 focus-visible:outline-civic-navy focus-visible:outline-offset-[-2px] rounded-lg"
        >
          <div className="flex items-start gap-4">
            {/* Date column */}
            <div className="text-center shrink-0 w-16">
              <p className="text-xs text-slate-500 uppercase tracking-wide">{day}</p>
              <p className="text-xl font-bold text-slate-800">{monthDay}</p>
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                {meeting.meeting_type.toLowerCase() !== 'regular' && (
                  <MeetingTypeBadge meetingType={meeting.meeting_type} compact />
                )}
                {meeting.presiding_officer && (
                  <span className="text-xs text-slate-400">
                    {meeting.presiding_officer}
                  </span>
                )}
              </div>

              <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-1.5 text-sm text-slate-600">
                <span>{meeting.agenda_item_count} items</span>
                {meeting.vote_count > 0 && <span>{meeting.vote_count} votes</span>}
                {visibleFlagCount > 0 && (
                  <span className="text-civic-amber">
                    {visibleFlagCount} contribution {visibleFlagCount === 1 ? 'record' : 'records'}
                  </span>
                )}
              </div>

              {topLabels.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {topLabels.map((t) => (
                    <TopicLabel key={t.label} label={t.label} />
                  ))}
                </div>
              )}
            </div>

            {/* Expand/collapse toggle — stops navigation */}
            {hasExpandContent && (
              <Collapsible.Trigger asChild>
                <button
                  type="button"
                  className="shrink-0 mt-1 p-1 -m-1 rounded hover:bg-slate-100 transition-colors cursor-pointer"
                  onClick={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                    setOpen((prev) => !prev)
                  }}
                  aria-label={open ? 'Collapse details' : 'Expand details'}
                >
                  <svg
                    className={`w-4 h-4 text-slate-400 transition-transform duration-200 ${
                      open ? 'rotate-90' : ''
                    }`}
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                  </svg>
                </button>
              </Collapsible.Trigger>
            )}
          </div>
        </Link>

        <Collapsible.Content className="collapsible-content overflow-hidden">
          <div className="px-4 pb-4 pt-0 border-t border-slate-100 mt-0">
            <div className="pt-3 space-y-3">
              {/* Topic label breakdown */}
              {allLabels.length > 0 && (
                <div>
                  <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1.5">
                    Topics
                  </h4>
                  <div className="flex flex-wrap gap-1.5">
                    {allLabels.map((t) => (
                      <span key={t.label} className="inline-flex items-center gap-1">
                        <TopicLabel label={t.label} />
                        <span className="text-xs text-slate-400">{t.count}</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Vote summary */}
              {meeting.vote_count > 0 && (
                <div>
                  <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">
                    Votes
                  </h4>
                  <p className="text-sm text-slate-600">
                    {meeting.vote_count} recorded {meeting.vote_count === 1 ? 'vote' : 'votes'}
                  </p>
                </div>
              )}

              {/* Campaign finance */}
              {visibleFlagCount > 0 && (
                <div>
                  <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">
                    Campaign Finance
                  </h4>
                  <p className="text-sm text-civic-amber">
                    {visibleFlagCount} contribution {visibleFlagCount === 1 ? 'record' : 'records'}
                    {' \u2014 '}
                    <Link
                      href={`/meetings/${meeting.id}`}
                      className="underline hover:text-civic-amber/80"
                      onClick={(e) => e.stopPropagation()}
                    >
                      view details
                    </Link>
                  </p>
                </div>
              )}
            </div>
          </div>
        </Collapsible.Content>
      </div>
    </Collapsible.Root>
  )
}
