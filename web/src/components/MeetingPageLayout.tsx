'use client'

import { useState, useMemo, useCallback, useRef } from 'react'
import type { AgendaItemWithMotions, ConflictFlag } from '@/lib/types'
import { getSignificance } from '@/lib/significance'
import type { Significance } from '@/lib/significance'
import MeetingToC from './MeetingToC'
import TopicBoard from './TopicBoard'
import LocalIssueFilterBar from './LocalIssueFilterBar'

interface MeetingPageLayoutProps {
  items: AgendaItemWithMotions[]
  flags: ConflictFlag[]
  children: React.ReactNode
}

export default function MeetingPageLayout({
  items,
  flags,
  children,
}: MeetingPageLayoutProps) {
  // ── Filter state (lifted from former MeetingDetailClient) ──
  const [activeFilter, setActiveFilter] = useState<string | null>(null)
  const [filteredItemIds, setFilteredItemIds] = useState<Set<string> | null>(null)

  function handleFilterChange(label: string | null, ids: Set<string> | null) {
    setActiveFilter(label)
    setFilteredItemIds(ids)
  }

  // ── Expand / highlight state ──────────────────────────────
  const [expandedItemIds, setExpandedItemIds] = useState<Set<string>>(new Set())
  const [highlightedItemId, setHighlightedItemId] = useState<string | null>(null)
  const highlightTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const scrollToAndExpand = useCallback((itemId: string) => {
    // Add to expanded set
    setExpandedItemIds(prev => {
      const next = new Set(prev)
      next.add(itemId)
      return next
    })

    // Scroll after React renders the expanded card
    requestAnimationFrame(() => {
      const el = document.getElementById(`agenda-item-${itemId}`)
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    })

    // Brief highlight glow
    setHighlightedItemId(itemId)
    if (highlightTimer.current) clearTimeout(highlightTimer.current)
    highlightTimer.current = setTimeout(() => setHighlightedItemId(null), 1500)
  }, [])

  // ── Shared significance map ───────────────────────────────
  const significanceMap = useMemo(() => {
    const map = new Map<string, Significance>()
    for (const item of items) {
      map.set(item.id, getSignificance(item, flags))
    }
    return map
  }, [items, flags])

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      <div className="lg:grid lg:grid-cols-[200px_1fr] lg:gap-10">
        {/* Sidebar — margin-style ToC, desktop only */}
        <aside>
          <MeetingToC
            items={items}
            significanceMap={significanceMap}
            activeFilter={activeFilter}
            filteredItemIds={filteredItemIds}
            onFilterChange={handleFilterChange}
            onItemClick={scrollToAndExpand}
            expandedItemIds={expandedItemIds}
          />
        </aside>

        {/* Main content column */}
        <div className="min-w-0">
          {children}

          {/* Mobile filter bar (hidden on desktop where sidebar has it) */}
          <div className="lg:hidden mb-6">
            <LocalIssueFilterBar
              items={items}
              activeFilter={activeFilter}
              onFilterChange={handleFilterChange}
            />
          </div>

          <TopicBoard
            items={items}
            flags={flags}
            significanceMap={significanceMap}
            activeFilter={activeFilter}
            filteredItemIds={filteredItemIds}
            expandedItemIds={expandedItemIds}
            highlightedItemId={highlightedItemId}
          />
        </div>
      </div>
    </div>
  )
}
