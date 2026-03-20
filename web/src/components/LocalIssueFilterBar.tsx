'use client'

import type { AgendaItemWithMotions } from '@/lib/types'
import { detectLocalIssues } from '@/lib/local-issues'
import type { LocalIssue } from '@/lib/local-issues'

interface LocalIssueFilterBarProps {
  items: AgendaItemWithMotions[]
  /** Currently active filter issue ID */
  activeFilter: string | null
  /** Callback when a filter is toggled */
  onFilterChange: (issueId: string | null, matchingItemIds: Set<string> | null) => void
}

interface IssueMatch {
  issue: LocalIssue
  matchCount: number
  matchingItemIds: Set<string>
}

/**
 * Row of local issue filter pills above the topic board.
 * Only shows issues with at least one match (no dead buttons).
 * Single-select: click to filter, click again to clear.
 *
 * Implementation note: uses individual toggle buttons in a role="group"
 * wrapper per resolved decision #8 (avoids Radix ToggleGroup ARIA issues).
 */
export default function LocalIssueFilterBar({
  items,
  activeFilter,
  onFilterChange,
}: LocalIssueFilterBarProps) {
  // Compute matches across all items
  const issueMatches: IssueMatch[] = []
  const issueMap = new Map<string, IssueMatch>()

  for (const item of items) {
    const issues = detectLocalIssues(item.title)
    for (const issue of issues) {
      let match = issueMap.get(issue.id)
      if (!match) {
        match = { issue, matchCount: 0, matchingItemIds: new Set() }
        issueMap.set(issue.id, match)
        issueMatches.push(match)
      }
      match.matchCount++
      match.matchingItemIds.add(item.id)
    }
  }

  // Sort by match count descending
  issueMatches.sort((a, b) => b.matchCount - a.matchCount)

  if (issueMatches.length === 0) return null

  return (
    <div className="mb-4">
      <div
        role="group"
        aria-label="Filter by local issue"
        className="flex flex-wrap gap-2"
      >
        {issueMatches.map(({ issue, matchCount, matchingItemIds }) => {
          const isActive = activeFilter === issue.id
          return (
            <button
              key={issue.id}
              role="switch"
              aria-checked={isActive}
              title={issue.context}
              onClick={() => {
                if (isActive) {
                  onFilterChange(null, null)
                } else {
                  onFilterChange(issue.id, matchingItemIds)
                }
              }}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                isActive
                  ? `${issue.color} ring-2 ring-offset-1 ring-civic-navy shadow-sm`
                  : `${issue.color} opacity-80 hover:opacity-100 hover:shadow-sm`
              }`}
            >
              {issue.label}
              <span className={`inline-flex items-center justify-center w-4 h-4 rounded-full text-[10px] font-bold ${
                isActive ? 'bg-white/50' : 'bg-black/10'
              }`}>
                {matchCount}
              </span>
            </button>
          )
        })}
      </div>
      {/* Live region for screen reader announcements */}
      {activeFilter && (
        <p role="status" className="sr-only">
          Filtered to {issueMatches.find(m => m.issue.id === activeFilter)?.issue.label}.
          {issueMatches.find(m => m.issue.id === activeFilter)?.matchCount} matching items.
        </p>
      )}
    </div>
  )
}
