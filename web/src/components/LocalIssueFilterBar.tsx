'use client'

import type { AgendaItemWithMotions } from '@/lib/types'
import { topicLabelColor } from '@/lib/topic-label-colors'

interface LocalIssueFilterBarProps {
  items: AgendaItemWithMotions[]
  /** Currently active filter topic label */
  activeFilter: string | null
  /** Callback when a filter is toggled */
  onFilterChange: (label: string | null, matchingItemIds: Set<string> | null) => void
}

interface TopicGroup {
  label: string
  color: string
  matchCount: number
  matchingItemIds: Set<string>
}

/**
 * Row of topic label filter pills above the topic board.
 * Groups agenda items by their LLM-assigned topic_label.
 * Only shows topics with at least one match (no dead buttons).
 * Single-select: click to filter, click again to clear.
 */
export default function LocalIssueFilterBar({
  items,
  activeFilter,
  onFilterChange,
}: LocalIssueFilterBarProps) {
  // Group items by topic_label
  const topicMap = new Map<string, TopicGroup>()

  for (const item of items) {
    const label = item.topic_label
    if (!label) continue

    let group = topicMap.get(label)
    if (!group) {
      group = {
        label,
        color: topicLabelColor(label),
        matchCount: 0,
        matchingItemIds: new Set(),
      }
      topicMap.set(label, group)
    }
    group.matchCount++
    group.matchingItemIds.add(item.id)
  }

  // Sort by match count descending
  const topicGroups = Array.from(topicMap.values())
    .sort((a, b) => b.matchCount - a.matchCount)

  if (topicGroups.length === 0) return null

  return (
    <div className="mb-4">
      <div
        role="group"
        aria-label="Filter by topic"
        className="flex flex-wrap gap-2"
      >
        {topicGroups.map(({ label, color, matchCount, matchingItemIds }) => {
          const isActive = activeFilter === label
          return (
            <button
              key={label}
              role="switch"
              aria-checked={isActive}
              onClick={() => {
                if (isActive) {
                  onFilterChange(null, null)
                } else {
                  onFilterChange(label, matchingItemIds)
                }
              }}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all cursor-pointer ${
                isActive
                  ? `${color} ring-2 ring-offset-1 ring-civic-navy shadow-sm`
                  : `${color} opacity-80 hover:opacity-100 hover:shadow-sm`
              }`}
            >
              {label}
              <span className={`inline-flex items-center justify-center w-4 h-4 rounded-full text-[10px] font-bold ${
                isActive ? 'bg-white/50' : 'bg-black/10'
              }`}>
                {matchCount}
              </span>
            </button>
          )
        })}
      </div>
      {/* Screen reader announcement */}
      {activeFilter && (
        <p role="status" className="sr-only">
          Filtered to {activeFilter}.
          {topicGroups.find(g => g.label === activeFilter)?.matchCount} matching items.
        </p>
      )}
    </div>
  )
}
