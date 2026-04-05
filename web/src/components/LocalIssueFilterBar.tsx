'use client'

import type { AgendaItemWithMotions } from '@/lib/types'

interface LocalIssueFilterBarProps {
  items: AgendaItemWithMotions[]
  /** Currently active filter topic label */
  activeFilter: string | null
  /** Callback when a filter is toggled */
  onFilterChange: (label: string | null, matchingItemIds: Set<string> | null) => void
}

interface TopicGroup {
  label: string
  matchCount: number
  matchingItemIds: Set<string>
}

/**
 * Structured topic filter for meeting pages.
 *
 * Design: Two tiers — prominent topics (3+ items) shown as full-width
 * clickable rows with proportional bar; minor topics (1-2 items) collapsed
 * into a quieter secondary row. This replaces the rainbow pill cloud with
 * a scannable hierarchy that answers "what is this meeting about?"
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
        matchCount: 0,
        matchingItemIds: new Set(),
      }
      topicMap.set(label, group)
    }
    group.matchCount++
    group.matchingItemIds.add(item.id)
  }

  // Sort by match count descending
  const allTopics = Array.from(topicMap.values())
    .sort((a, b) => b.matchCount - a.matchCount)

  if (allTopics.length === 0) return null

  const maxCount = allTopics[0]?.matchCount ?? 1

  // Split into prominent (2+ items) and minor (1 item)
  const prominent = allTopics.filter(t => t.matchCount >= 2)
  const minor = allTopics.filter(t => t.matchCount < 2)

  function handleClick(label: string, matchingItemIds: Set<string>) {
    if (activeFilter === label) {
      onFilterChange(null, null)
    } else {
      onFilterChange(label, matchingItemIds)
    }
  }

  return (
    <div className="mb-5" role="group" aria-label="Filter by topic">
      {/* Prominent topics — full rows with proportion bar */}
      {prominent.length > 0 && (
        <div className="space-y-1 mb-2">
          {prominent.map(({ label, matchCount, matchingItemIds }) => {
            const isActive = activeFilter === label
            const barWidth = Math.max(8, (matchCount / maxCount) * 100)

            return (
              <button
                key={label}
                role="switch"
                aria-checked={isActive}
                onClick={() => handleClick(label, matchingItemIds)}
                className={`group w-full flex items-center gap-3 px-3 py-2 rounded-md text-left transition-all cursor-pointer ${
                  isActive
                    ? 'bg-civic-navy/[0.08] ring-1 ring-civic-navy/20'
                    : 'hover:bg-slate-50'
                }`}
              >
                {/* Proportion bar */}
                <div className="w-10 sm:w-16 shrink-0">
                  <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${
                        isActive ? 'bg-civic-navy' : 'bg-slate-300 group-hover:bg-civic-navy/50'
                      }`}
                      style={{ width: `${barWidth}%` }}
                    />
                  </div>
                </div>
                <span className={`text-sm flex-1 ${
                  isActive ? 'font-medium text-civic-navy' : 'text-slate-700'
                }`}>
                  {label}
                </span>
                <span className={`text-xs tabular-nums shrink-0 ${
                  isActive ? 'text-civic-navy font-medium' : 'text-slate-400'
                }`}>
                  {matchCount}
                </span>
              </button>
            )
          })}
        </div>
      )}

      {/* Minor topics — compact inline list */}
      {minor.length > 0 && (
        <div className="flex flex-wrap gap-x-1 gap-y-0.5 px-3">
          {minor.map(({ label, matchingItemIds }) => {
            const isActive = activeFilter === label
            return (
              <button
                key={label}
                role="switch"
                aria-checked={isActive}
                onClick={() => handleClick(label, matchingItemIds)}
                className={`text-xs py-0.5 px-1.5 rounded transition-colors cursor-pointer ${
                  isActive
                    ? 'text-civic-navy font-medium bg-civic-navy/[0.08]'
                    : 'text-slate-400 hover:text-slate-600'
                }`}
              >
                {label}
              </button>
            )
          })}
        </div>
      )}

      {/* Screen reader announcement */}
      {activeFilter && (
        <p role="status" className="sr-only">
          Filtered to {activeFilter}.
          {allTopics.find(g => g.label === activeFilter)?.matchCount} matching items.
        </p>
      )}
    </div>
  )
}
