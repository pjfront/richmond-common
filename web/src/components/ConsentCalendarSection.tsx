'use client'

import { useState } from 'react'
import * as Collapsible from '@radix-ui/react-collapsible'
import type { AgendaItemWithMotions } from '@/lib/types'
import AgendaItemCard from './AgendaItemCard'

interface ConsentCalendarSectionProps {
  items: AgendaItemWithMotions[]
  onCategoryClick?: (category: string) => void
  selectedCategory?: string | null
  /** When true, auto-expand the consent calendar (e.g. when a filter matches consent items) */
  forceExpanded?: boolean
  /** Item IDs expanded via ToC click — also forces section open if any match */
  expandedItemIds?: Set<string>
  /** Item currently highlighted after scroll-to */
  highlightedItemId?: string | null
}

/** Preserve the recorded consent grouping and incoming agenda order. */
export default function ConsentCalendarSection({
  items,
  onCategoryClick,
  selectedCategory,
  forceExpanded = false,
  expandedItemIds,
  highlightedItemId,
}: ConsentCalendarSectionProps) {
  const [manualExpanded, setManualExpanded] = useState(false)
  // Auto-expand when any consent item was clicked in the ToC
  const hasExpandedChild = expandedItemIds
    ? items.some(i => expandedItemIds.has(i.id))
    : false
  const expanded = manualExpanded || forceExpanded || hasExpandedChild

  if (items.length === 0) return null

  return (
    <Collapsible.Root open={expanded} onOpenChange={setManualExpanded} asChild>
      <section className="mb-6">
        <h2>
          <Collapsible.Trigger asChild>
            <button
              type="button"
              className="flex min-h-11 min-w-11 items-center gap-2 text-lg font-semibold text-slate-800 mb-2 hover:text-civic-navy focus-visible:outline-2 focus-visible:outline-civic-navy cursor-pointer"
            >
              Consent Calendar
              <span className="text-sm font-normal text-slate-500">
                ({items.length} agenda {items.length === 1 ? 'entry' : 'entries'})
              </span>
              <span className="text-sm text-slate-500" aria-hidden="true">
                {expanded ? '\u2212' : '+'}
              </span>
            </button>
          </Collapsible.Trigger>
        </h2>
        <p className="text-sm text-slate-600 mb-3">
          Listed on the consent calendar. Open an entry for its recorded motions and source text.
        </p>
        <Collapsible.Content className="space-y-3">
          {items.map(item => (
            <AgendaItemCard
              key={item.id}
              item={item}
              significance="consent"
              onCategoryClick={onCategoryClick}
              selectedCategory={selectedCategory}
              forceExpanded={expandedItemIds?.has(item.id)}
              highlighted={highlightedItemId === item.id}
            />
          ))}
        </Collapsible.Content>
      </section>
    </Collapsible.Root>
  )
}
