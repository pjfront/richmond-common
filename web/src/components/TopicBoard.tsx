'use client'

import { useMemo } from 'react'
import type { AgendaItemWithMotions, ConflictFlag } from '@/lib/types'
import { isProcedural, hasSplitVote, getSplitVoteMargin } from '@/lib/significance'
import type { Significance } from '@/lib/significance'
import ConsentCalendarSection from './ConsentCalendarSection'
import ProceduralStrip from './ProceduralStrip'
import AgendaItemCard from './AgendaItemCard'

interface TopicBoardProps {
  items: AgendaItemWithMotions[]
  flags: ConflictFlag[]
  /** Pre-computed significance map (shared with MeetingToC) */
  significanceMap: Map<string, Significance>
  /** External filter from LocalIssueFilterBar / MeetingToC */
  activeFilter?: string | null
  /** Matching item IDs from the active filter */
  filteredItemIds?: Set<string> | null
  /** Currently expanded item IDs (driven by MeetingPageLayout) */
  expandedItemIds?: Set<string>
  /** Item currently highlighted after scroll-to */
  highlightedItemId?: string | null
}

export default function TopicBoard({
  items,
  flags,
  significanceMap,
  activeFilter,
  filteredItemIds,
  expandedItemIds,
  highlightedItemId,
}: TopicBoardProps) {
  const hasDiscussionData = useMemo(
    () => items.some(i => i.public_comment_count > 0),
    [items],
  )

  // Partition items by significance
  const { consentItems, proceduralItems, substantiveItems } = useMemo(() => {
    const consent: AgendaItemWithMotions[] = []
    const procedural: AgendaItemWithMotions[] = []
    const substantive: AgendaItemWithMotions[] = []

    for (const item of items) {
      const sig = significanceMap.get(item.id) ?? 'standard'
      if (sig === 'procedural') {
        procedural.push(item)
      } else if (sig === 'consent') {
        consent.push(item)
      } else {
        substantive.push(item)
      }
    }

    return { consentItems: consent, proceduralItems: procedural, substantiveItems: substantive }
  }, [items, significanceMap])

  // Apply topic filter
  const filteredSubstantive = useMemo(() => {
    if (!filteredItemIds) return substantiveItems
    return substantiveItems.filter(i => filteredItemIds.has(i.id))
  }, [substantiveItems, filteredItemIds])

  const filteredConsent = useMemo(() => {
    if (!filteredItemIds) return consentItems
    return consentItems.filter(i => filteredItemIds.has(i.id))
  }, [consentItems, filteredItemIds])

  const filteredProcedural = useMemo(() => {
    if (!filteredItemIds) return proceduralItems
    return proceduralItems.filter(i => filteredItemIds.has(i.id))
  }, [proceduralItems, filteredItemIds])

  // Sort: Most Discussed (by comment count, then vote margin), or agenda order fallback
  const sortedItems = useMemo(() => {
    if (!hasDiscussionData) {
      // Agenda order fallback
      return [...filteredSubstantive].sort((a, b) =>
        (a.item_number ?? '').localeCompare(b.item_number ?? '', undefined, { numeric: true }),
      )
    }

    return [...filteredSubstantive].sort((a, b) => {
      const commDiff = b.public_comment_count - a.public_comment_count
      if (commDiff !== 0) return commDiff
      const aMargin = hasSplitVote(a) ? (getSplitVoteMargin(a) ?? 99) : 99
      const bMargin = hasSplitVote(b) ? (getSplitVoteMargin(b) ?? 99) : 99
      return aMargin - bMargin
    })
  }, [filteredSubstantive, hasDiscussionData])

  const isFiltered = !!activeFilter
  const topItem = sortedItems[0]?.public_comment_count > 0 ? sortedItems[0] : null

  return (
    <div>
      {/* Item count / filter indicator */}
      <div className="text-sm text-slate-500 mb-4">
        {isFiltered ? (
          <span>
            {filteredSubstantive.length + filteredConsent.length} matching items
          </span>
        ) : (
          <span>
            {substantiveItems.length} items
            {consentItems.length > 0 && ` · ${consentItems.length} consent`}
          </span>
        )}
      </div>

      {/* Substantive items — collapsed text rows by default, expandable to full cards */}
      <div className="divide-y divide-slate-100">
        {sortedItems.map((item) => {
          const significance = significanceMap.get(item.id) ?? 'standard'
          const itemFlags = flags.filter(f => f.agenda_item_id === item.id)
          const isMostDiscussed = hasDiscussionData && item === topItem

          return (
            <AgendaItemCard
              key={item.id}
              item={item}
              significance={significance}
              mostDiscussed={isMostDiscussed}
              flagCount={itemFlags.length}
              forceExpanded={expandedItemIds?.has(item.id)}
              highlighted={highlightedItemId === item.id}
            />
          )
        })}
      </div>

      {/* Consent calendar */}
      <ConsentCalendarSection
        items={filteredConsent}
        forceExpanded={isFiltered && filteredConsent.length > 0 && filteredSubstantive.length === 0}
      />

      {/* Procedural strip */}
      {activeFilter ? (
        filteredProcedural.length > 0 && <ProceduralStrip items={filteredProcedural} />
      ) : (
        <ProceduralStrip items={proceduralItems} />
      )}

      {/* Empty state */}
      {isFiltered && sortedItems.length === 0 && filteredConsent.length === 0 && filteredProcedural.length === 0 && (
        <p className="text-sm text-slate-400 italic py-4">
          No matching items.
        </p>
      )}
    </div>
  )
}
