'use client'

import { useState } from 'react'
import type { AgendaItemWithMotions, ConflictFlag } from '@/lib/types'
import LocalIssueFilterBar from './LocalIssueFilterBar'
import TopicBoard from './TopicBoard'

interface MeetingDetailClientProps {
  items: AgendaItemWithMotions[]
  flags: ConflictFlag[]
}

/**
 * Client wrapper for the interactive meeting detail section.
 * Manages local issue filter state and passes it to TopicBoard.
 * Manages local issue filter state and passes it to TopicBoard.
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
