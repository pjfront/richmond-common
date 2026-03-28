'use client'

import { useState } from 'react'
import type { AgendaItemWithMotions } from '@/lib/types'
import CategoryBadge from './CategoryBadge'

interface ConsentCalendarSectionProps {
  items: AgendaItemWithMotions[]
  onCategoryClick?: (category: string) => void
  selectedCategory?: string | null
  /** When true, auto-expand the consent calendar (e.g. when a filter matches only consent items) */
  forceExpanded?: boolean
}

/**
 * Compact consent calendar — one line per item, title only.
 * Expandable to show full details for pulled items.
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
          {expanded ? '−' : '+'}
        </span>
      </button>
      {!expanded && (
        <p className="text-sm text-slate-500">
          Approved as a group without individual discussion.
        </p>
      )}
      {expanded && (
        <div className="space-y-1">
          {items.map(item => (
            <div
              key={item.id}
              className="flex items-center gap-2 py-1.5 px-3 text-sm text-slate-600 bg-slate-50 rounded"
            >
              <span className="text-xs font-mono text-slate-400 shrink-0">
                {item.item_number}
              </span>
              <span className="flex-1 min-w-0 truncate">{item.title}</span>
              <CategoryBadge
                category={item.category}
                onClick={onCategoryClick}
                active={selectedCategory === item.category}
              />
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
