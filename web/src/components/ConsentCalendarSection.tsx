'use client'

import { useState } from 'react'
import type { AgendaItemWithMotions } from '@/lib/types'
import AgendaItemCard from './AgendaItemCard'

interface ConsentCalendarSectionProps {
  items: AgendaItemWithMotions[]
  onCategoryClick?: (category: string) => void
  selectedCategory?: string | null
  /** When true, auto-expand the consent calendar (e.g. when a filter matches only consent items) */
  forceExpanded?: boolean
}

/**
 * Consent calendar section — collapsible group of agenda items.
 * Uses AgendaItemCard (which starts collapsed for consent items)
 * so each item can be individually expanded to see summaries, votes, etc.
 */
export default function ConsentCalendarSection({
  items,
  onCategoryClick,
  selectedCategory,
  forceExpanded = false,
}: ConsentCalendarSectionProps) {
  const [manualExpanded, setManualExpanded] = useState(false)
  const expanded = manualExpanded || forceExpanded

  if (items.length === 0) return null

  return (
    <section className="mb-6">
      <button
        onClick={() => setManualExpanded(!expanded)}
        className="flex items-center gap-2 text-lg font-semibold text-slate-800 mb-2 hover:text-civic-navy transition-colors cursor-pointer"
      >
        Consent Calendar
        <span className="text-sm font-normal text-slate-400">
          ({items.length} {items.length === 1 ? 'item' : 'items'})
        </span>
        <span className="text-sm text-slate-400">
          {expanded ? '\u2212' : '+'}
        </span>
      </button>
      {!expanded && (
        <p className="text-sm text-slate-500">
          Approved as a group without individual discussion.
        </p>
      )}
      {expanded && (
        <div className="space-y-3">
          {items.map(item => (
            <AgendaItemCard
              key={item.id}
              item={item}
              significance="consent"
              onCategoryClick={onCategoryClick}
              selectedCategory={selectedCategory}
            />
          ))}
        </div>
      )}
    </section>
  )
}
