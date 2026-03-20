'use client'

import { useState } from 'react'
import type { AgendaItemWithMotions, ConflictFlag } from '@/lib/types'
import HeroItem from './HeroItem'
import LocalIssueFilterBar from './LocalIssueFilterBar'
import TopicBoard from './TopicBoard'

interface MeetingDetailClientProps {
  items: AgendaItemWithMotions[]
  flags: ConflictFlag[]
}

/**
 * Client wrapper for the interactive meeting detail section.
 * Manages local issue filter state and passes it to TopicBoard.
 * HeroItem sits above the filter bar; TopicBoard below.
 */
export default function MeetingDetailClient({ items, flags }: MeetingDetailClientProps) {
  const [activeFilter, setActiveFilter] = useState<string | null>(null)
  const [filteredItemIds, setFilteredItemIds] = useState<Set<string> | null>(null)

  function handleFilterChange(issueId: string | null, itemIds: Set<string> | null) {
    setActiveFilter(issueId)
    setFilteredItemIds(itemIds)
  }

  return (
    <>
      <HeroItem items={items} flags={flags} />
      <LocalIssueFilterBar
        items={items}
        activeFilter={activeFilter}
        onFilterChange={handleFilterChange}
      />
      <TopicBoard
        items={items}
        flags={flags}
        activeFilter={activeFilter}
        filteredItemIds={filteredItemIds}
      />
    </>
  )
}
