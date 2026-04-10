'use client'

import { useState } from 'react'
import * as Collapsible from '@radix-ui/react-collapsible'
import type { AgendaItemWithMotions } from '@/lib/types'
import type { Significance } from '@/lib/significance'
import { getOverallResult, isProcedural } from '@/lib/significance'
import type { OverallResult } from '@/lib/significance'

interface MeetingToCProps {
  items: AgendaItemWithMotions[]
  significanceMap: Map<string, Significance>
  activeFilter: string | null
  filteredItemIds: Set<string> | null
  onFilterChange: (label: string | null, matchingItemIds: Set<string> | null) => void
  onItemClick: (itemId: string) => void
  expandedItemIds: Set<string>
}

// ── Result dot colors ──────────────────────────────────────

const DOT_COLORS: Record<OverallResult, string> = {
  passed: 'bg-vote-aye',
  failed: 'bg-vote-nay',
  mixed: 'bg-amber-400',
  none: 'bg-slate-300',
}

function ResultDot({ result }: { result: OverallResult }) {
  return (
    <span
      className={`w-2 h-2 rounded-full shrink-0 ${DOT_COLORS[result]}`}
      aria-hidden="true"
    />
  )
}

// ── Short name helper ──────────────────────────────────────

function shortName(item: AgendaItemWithMotions): string {
  const name = item.summary_headline ?? item.title
  if (name.length <= 55) return name
  return name.slice(0, 52) + '...'
}

// ── Topic filter (compact sidebar version) ─────────────────

interface TopicGroup {
  label: string
  matchCount: number
  matchingItemIds: Set<string>
}

function buildTopicGroups(items: AgendaItemWithMotions[]): TopicGroup[] {
  const map = new Map<string, TopicGroup>()
  for (const item of items) {
    if (!item.topic_label) continue
    let group = map.get(item.topic_label)
    if (!group) {
      group = { label: item.topic_label, matchCount: 0, matchingItemIds: new Set() }
      map.set(item.topic_label, group)
    }
    group.matchCount++
    group.matchingItemIds.add(item.id)
  }
  return Array.from(map.values()).sort((a, b) => b.matchCount - a.matchCount)
}

// ── Main component ─────────────────────────────────────────

export default function MeetingToC({
  items,
  significanceMap,
  activeFilter,
  filteredItemIds,
  onFilterChange,
  onItemClick,
  expandedItemIds,
}: MeetingToCProps) {
  const [consentOpen, setConsentOpen] = useState(false)

  // Partition items
  const substantive: AgendaItemWithMotions[] = []
  const consent: AgendaItemWithMotions[] = []

  for (const item of items) {
    const sig = significanceMap.get(item.id) ?? 'standard'
    if (sig === 'procedural') continue
    if (sig === 'consent') {
      consent.push(item)
    } else {
      substantive.push(item)
    }
  }

  const topics = buildTopicGroups(items.filter(i => !isProcedural(i)))
  const isItemVisible = (id: string) => !filteredItemIds || filteredItemIds.has(id)

  return (
    <nav
      aria-label="Agenda items"
      className="sticky top-24 max-h-[calc(100vh-8rem)] overflow-y-auto hidden lg:block"
    >
      {/* Section label */}
      <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-3">
        On this page
      </p>

      {/* Item list with vertical line */}
      <div className="border-l border-slate-200 pl-3 space-y-0.5">
        {substantive.map((item) => {
          const result = getOverallResult(item)
          const visible = isItemVisible(item.id)
          const isExpanded = expandedItemIds.has(item.id)

          return (
            <button
              key={item.id}
              onClick={() => visible && onItemClick(item.id)}
              disabled={!visible}
              className={`w-full flex items-center gap-2 py-1 text-left transition-colors cursor-pointer disabled:cursor-default disabled:opacity-30 ${
                isExpanded
                  ? 'text-civic-navy font-medium -ml-px border-l-2 border-l-civic-navy pl-[11px]'
                  : 'text-slate-500 hover:text-civic-navy'
              }`}
            >
              <ResultDot result={result} />
              <span className="text-[13px] leading-snug truncate">
                {shortName(item)}
              </span>
            </button>
          )
        })}

        {/* Consent calendar group */}
        {consent.length > 0 && (
          <Collapsible.Root open={consentOpen} onOpenChange={setConsentOpen}>
            <Collapsible.Trigger asChild>
              <button className="w-full flex items-center gap-2 py-1 text-left transition-colors cursor-pointer text-slate-500 hover:text-civic-navy">
                <ResultDot result="passed" />
                <span className="text-[13px] leading-snug flex-1">
                  Consent ({consent.length})
                </span>
                <span className="p-1 -mr-1">
                  <svg
                    className={`h-3.5 w-3.5 text-slate-400 shrink-0 transition-transform ${consentOpen ? 'rotate-180' : ''}`}
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                    aria-hidden="true"
                  >
                    <path
                      fillRule="evenodd"
                      d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.168l3.71-3.938a.75.75 0 1 1 1.08 1.04l-4.25 4.5a.75.75 0 0 1-1.08 0l-4.25-4.5a.75.75 0 0 1 .02-1.06Z"
                      clipRule="evenodd"
                    />
                  </svg>
                </span>
              </button>
            </Collapsible.Trigger>
            <Collapsible.Content className="collapsible-content overflow-hidden">
              <div className="pl-3 space-y-0.5">
                {consent.map((item) => {
                  const visible = isItemVisible(item.id)
                  return (
                    <button
                      key={item.id}
                      onClick={() => visible && onItemClick(item.id)}
                      disabled={!visible}
                      className="w-full flex items-center gap-2 py-0.5 text-left transition-colors cursor-pointer disabled:cursor-default disabled:opacity-30 text-slate-400 hover:text-civic-navy"
                    >
                      <span className="w-1.5 h-1.5 rounded-full bg-slate-300 shrink-0" aria-hidden="true" />
                      <span className="text-xs leading-snug truncate">
                        {shortName(item)}
                      </span>
                    </button>
                  )
                })}
              </div>
            </Collapsible.Content>
          </Collapsible.Root>
        )}
      </div>

      {/* Topic filter tags */}
      {topics.length > 0 && (
        <div className="mt-4 pt-3 border-t border-slate-100">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-semibold uppercase tracking-widest text-slate-400">
              Topics
            </p>
            {activeFilter && (
              <button
                onClick={() => onFilterChange(null, null)}
                className="text-[11px] text-slate-400 hover:text-slate-600 transition-colors cursor-pointer"
              >
                Clear
              </button>
            )}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {topics.map(({ label, matchCount, matchingItemIds }) => {
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
                  className={`text-xs py-1 px-2.5 rounded-full border transition-colors cursor-pointer ${
                    isActive
                      ? 'bg-civic-navy text-white border-civic-navy'
                      : 'bg-slate-50 text-slate-600 border-slate-200 hover:text-civic-navy hover:border-civic-navy/30 hover:bg-slate-100'
                  }`}
                >
                  {label}
                  {matchCount > 1 && (
                    <span className={`ml-1.5 text-[11px] tabular-nums rounded-full px-1.5 ${
                      isActive ? 'bg-white/20 text-white' : 'bg-slate-200/80 text-slate-500'
                    }`}>
                      {matchCount}
                    </span>
                  )}
                </button>
              )
            })}
          </div>

          {/* Screen reader status */}
          {activeFilter && (
            <p role="status" className="sr-only">
              Filtered to {activeFilter}.
            </p>
          )}
        </div>
      )}
    </nav>
  )
}
