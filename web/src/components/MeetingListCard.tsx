'use client'

import { useState } from 'react'
import Link from 'next/link'
import * as Collapsible from '@radix-ui/react-collapsible'
import MeetingTypeBadge, { getMeetingTypeBorderAccent } from './MeetingTypeBadge'
import TopicLabel from './TopicLabel'
import type { MeetingWithCounts } from '@/lib/types'

interface MeetingListCardProps {
  meeting: MeetingWithCounts
}

function formatDayDate(dateStr: string): { weekday: string; month: string; day: string } {
  const date = new Date(dateStr + 'T00:00:00')
  return {
    weekday: date.toLocaleDateString('en-US', { weekday: 'short' }),
    month: date.toLocaleDateString('en-US', { month: 'long' }),
    day: date.toLocaleDateString('en-US', { day: 'numeric' }),
  }
}

/** Source-linked meeting entry, with a separate accessible topic disclosure. */
export default function MeetingListCard({ meeting }: MeetingListCardProps) {
  const [open, setOpen] = useState(false)
  const { weekday, month, day } = formatDayDate(meeting.meeting_date)
  const borderAccent = getMeetingTypeBorderAccent(meeting.meeting_type)
  const topLabels = meeting.top_topic_labels.slice(0, 4)
  const allLabels = meeting.all_topic_labels

  return (
    <Collapsible.Root open={open} onOpenChange={setOpen}>
      <div
        className={`bg-white rounded-lg border border-slate-200 border-l-4 ${borderAccent} transition-shadow motion-reduce:transition-none ${
          open ? 'shadow-sm border-slate-300' : 'hover:border-slate-300 hover:shadow-sm'
        }`}
      >
        <div className="flex items-start">
          <Link
            href={`/meetings/${meeting.id}`}
            className="block min-w-0 flex-1 px-4 sm:px-5 py-4 focus-visible:outline-2 focus-visible:outline-civic-navy focus-visible:outline-offset-[-2px] rounded-lg"
          >
            <div className="flex items-start gap-3 sm:gap-4">
              <div className="text-center shrink-0 w-14 sm:w-20">
                <p className="text-xs text-slate-500 uppercase tracking-wide">{weekday}</p>
                <p className="text-sm text-slate-500">{month}</p>
                <p className="text-2xl font-bold text-slate-800 leading-tight">{day}</p>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  {meeting.meeting_type.toLowerCase() !== 'regular' && (
                    <MeetingTypeBadge meetingType={meeting.meeting_type} compact />
                  )}
                  {meeting.presiding_officer && (
                    <span className="text-xs text-slate-500">{meeting.presiding_officer}</span>
                  )}
                </div>
                <p className="mt-1.5 text-sm text-slate-600">
                  {meeting.agenda_item_count > 0
                    ? `${meeting.agenda_item_count} agenda ${meeting.agenda_item_count === 1 ? 'entry' : 'entries'} in this archive`
                    : 'No agenda entries in this archive'}
                </p>
                {topLabels.length > 0 && (
                  <div className="mt-2">
                    <p className="text-xs text-slate-500 mb-1.5">Topics assigned by AI</p>
                    <div className="flex flex-wrap gap-1.5">
                      {topLabels.map(topic => <TopicLabel key={topic.label} label={topic.label} />)}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </Link>
          {allLabels.length > 0 && (
            <Collapsible.Trigger asChild>
              <button
                type="button"
                className="mt-3 mr-2 flex h-11 w-11 shrink-0 items-center justify-center rounded hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-civic-navy"
                aria-label={`${open ? 'Hide' : 'Show'} ${allLabels.length} ${allLabels.length === 1 ? 'topic' : 'topics'} assigned by AI for ${month} ${day}`}
              >
                <svg
                  className={`h-4 w-4 text-slate-500 transition-transform motion-reduce:transition-none ${open ? 'rotate-90' : ''}`}
                  aria-hidden="true"
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
        {allLabels.length > 0 && (
          <Collapsible.Content className="collapsible-content overflow-hidden motion-reduce:animate-none">
            <div className="px-4 py-3 border-t border-slate-100">
              <p className="text-xs font-medium text-slate-500 mb-2">
                {allLabels.length} {allLabels.length === 1 ? 'topic' : 'topics'} assigned by AI · Counts refer to agenda entries in this archive
              </p>
              <div className="flex flex-wrap gap-2">
                {allLabels.map(topic => (
                  <span key={topic.label} className="inline-flex items-center gap-1">
                    <TopicLabel label={topic.label} />
                    <span className="text-xs text-slate-500">{topic.count}</span>
                  </span>
                ))}
              </div>
            </div>
          </Collapsible.Content>
        )}
      </div>
    </Collapsible.Root>
  )
}
