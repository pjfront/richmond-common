'use client'

import { useState, useMemo } from 'react'
import type { AgendaItemWithMotions, ConflictFlag } from '@/lib/types'
import { getSignificance, isProcedural, hasSplitVote, getSplitVoteMargin } from '@/lib/significance'
import type { Significance } from '@/lib/significance'
import CategorySection from './CategorySection'
import ConsentCalendarSection from './ConsentCalendarSection'
import ProceduralStrip from './ProceduralStrip'
import AgendaItemCard from './AgendaItemCard'
import { formatCategory } from './CategoryBadge'

interface TopicBoardProps {
  items: AgendaItemWithMotions[]
  flags: ConflictFlag[]
  /** External filter from LocalIssueFilterBar */
  activeFilter?: string | null
  /** Matching item IDs from the active filter */
  filteredItemIds?: Set<string> | null
}

export default function TopicBoard({
  items,
  flags,
  activeFilter,
  filteredItemIds,
}: TopicBoardProps) {
  // Only show "Most Discussed" when at least one item has public comments recorded
  const hasDiscussionData = useMemo(
    () => items.some(i => i.public_comment_count > 0),
    [items],
  )
  const [viewMode, setViewMode] = useState<'discussed' | 'topic' | 'sequential'>(
    hasDiscussionData ? 'discussed' : 'topic',
  )
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)

  function handleCategoryClick(category: string) {
    setSelectedCategory(prev => (prev === category ? null : category))
  }

  // Compute significance for all items
  const significanceMap = useMemo(() => {
    const map = new Map<string, Significance>()
    for (const item of items) {
      map.set(item.id, getSignificance(item, flags))
    }
    return map
  }, [items, flags])

  // Partition items
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

  // Apply filters
  const filteredSubstantive = useMemo(() => {
    let filtered = substantiveItems

    // Local issue filter
    if (filteredItemIds) {
      filtered = filtered.filter(i => filteredItemIds.has(i.id))
    }

    // Category filter
    if (selectedCategory) {
      filtered = filtered.filter(i => i.category === selectedCategory)
    }

    return filtered
  }, [substantiveItems, filteredItemIds, selectedCategory])

  // Group by category, sorted by controversy score (tiebreak: item count)
  const categoryGroups = useMemo(() => {
    const groups = new Map<string, AgendaItemWithMotions[]>()
    for (const item of filteredSubstantive) {
      const cat = item.category ?? 'other'
      const existing = groups.get(cat) ?? []
      existing.push(item)
      groups.set(cat, existing)
    }

    // Score: public comments weighted highest, then split votes, then pulled/financial
    function controversy(categoryItems: AgendaItemWithMotions[]): number {
      let score = 0
      for (const item of categoryItems) {
        score += item.public_comment_count
        if (hasSplitVote(item)) {
          score += 4
          const margin = getSplitVoteMargin(item)
          if (margin !== null && margin <= 3) score += (4 - margin)
        }
        if (item.was_pulled_from_consent) score += 2
        if (flags.some(f => f.agenda_item_id === item.id)) score += 1
      }
      return score
    }

    return Array.from(groups.entries())
      .sort((a, b) => {
        const scoreA = controversy(a[1])
        const scoreB = controversy(b[1])
        if (scoreB !== scoreA) return scoreB - scoreA
        return b[1].length - a[1].length
      })
  }, [filteredSubstantive, flags])

  // Filter consent items too when local issue filter is active
  const filteredConsent = useMemo(() => {
    if (!filteredItemIds) return consentItems
    return consentItems.filter(i => filteredItemIds.has(i.id))
  }, [consentItems, filteredItemIds])

  const isFiltered = !!activeFilter || !!selectedCategory

  return (
    <div>
      {/* View toggle + filter controls */}
      <div className="flex items-center justify-between mb-4">
        <div className="text-sm text-slate-500">
          {isFiltered ? (
            <span>
              {filteredSubstantive.length + filteredConsent.length} matching items
              {selectedCategory && (
                <>
                  {' '}in <span className="font-medium text-slate-700">{formatCategory(selectedCategory)}</span>
                </>
              )}
              {' '}&middot;{' '}
              <button
                onClick={() => setSelectedCategory(null)}
                className="text-civic-navy hover:underline"
              >
                clear{selectedCategory ? ' category' : ''} filter
              </button>
            </span>
          ) : (
            <span>
              {substantiveItems.length} substantive items
              {consentItems.length > 0 && ` · ${consentItems.length} consent`}
              {proceduralItems.length > 0 && ` · ${proceduralItems.length} procedural`}
            </span>
          )}
        </div>
        <div className="flex gap-1 bg-slate-100 rounded-md p-0.5">
          {hasDiscussionData && (
            <button
              onClick={() => setViewMode('discussed')}
              className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                viewMode === 'discussed'
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              Most Discussed
            </button>
          )}
          <button
            onClick={() => setViewMode('topic')}
            className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
              viewMode === 'topic'
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            By Topic
          </button>
          <button
            onClick={() => setViewMode('sequential')}
            className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
              viewMode === 'sequential'
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            Agenda Order
          </button>
        </div>
      </div>

      {viewMode === 'discussed' ? (
        /* Most Discussed view — items sorted by public comment count + controversy */
        <div className="space-y-2">
          {[...filteredSubstantive]
            .sort((a, b) => {
              // Primary: public comment count
              const commDiff = b.public_comment_count - a.public_comment_count
              if (commDiff !== 0) return commDiff
              // Secondary: split vote margin (closer = more controversial)
              const aMargin = hasSplitVote(a) ? (getSplitVoteMargin(a) ?? 99) : 99
              const bMargin = hasSplitVote(b) ? (getSplitVoteMargin(b) ?? 99) : 99
              return aMargin - bMargin
            })
            .map(item => {
              const significance = significanceMap.get(item.id) ?? 'standard'
              const itemFlags = flags.filter(f => f.agenda_item_id === item.id)
              return (
                <AgendaItemCard
                  key={item.id}
                  item={item}
                  significance={significance}
                  flagCount={itemFlags.length}
                  onCategoryClick={handleCategoryClick}
                  selectedCategory={selectedCategory}
                />
              )
            })}

          {/* Consent calendar */}
          <ConsentCalendarSection
            items={filteredConsent}
            onCategoryClick={handleCategoryClick}
            selectedCategory={selectedCategory}
          />

          {!isFiltered && <ProceduralStrip items={proceduralItems} />}

          {isFiltered && filteredSubstantive.length === 0 && filteredConsent.length === 0 && (
            <p className="text-sm text-slate-400 italic py-4">
              No matching items.{' '}
              <button
                onClick={() => setSelectedCategory(null)}
                className="text-civic-navy hover:underline not-italic"
              >
                Clear filter
              </button>
            </p>
          )}
        </div>
      ) : viewMode === 'topic' ? (
        <>
          {/* Category-grouped sections */}
          {categoryGroups.map(([category, groupItems]) => (
            <CategorySection
              key={category}
              category={category}
              items={groupItems}
              significanceMap={significanceMap}
              flags={flags}
              onCategoryClick={handleCategoryClick}
              selectedCategory={selectedCategory}
            />
          ))}

          {/* Consent calendar */}
          <ConsentCalendarSection
            items={filteredConsent}
            onCategoryClick={handleCategoryClick}
            selectedCategory={selectedCategory}
          />

          {/* Procedural strip */}
          {!isFiltered && <ProceduralStrip items={proceduralItems} />}

          {/* Empty filter state */}
          {isFiltered && filteredSubstantive.length === 0 && filteredConsent.length === 0 && (
            <p className="text-sm text-slate-400 italic py-4">
              No matching items.{' '}
              <button
                onClick={() => setSelectedCategory(null)}
                className="text-civic-navy hover:underline not-italic"
              >
                Clear filter
              </button>
            </p>
          )}
        </>
      ) : (
        /* Sequential view — flat list by item number, for following along in a live meeting */
        <div className="space-y-2">
          {items
            .filter(i => !isProcedural(i))
            .map(item => {
              const significance = significanceMap.get(item.id) ?? 'standard'
              const itemFlags = flags.filter(f => f.agenda_item_id === item.id)
              return (
                <AgendaItemCard
                  key={item.id}
                  item={item}
                  significance={significance}
                  flagCount={itemFlags.length}
                  onCategoryClick={handleCategoryClick}
                  selectedCategory={selectedCategory}
                />
              )
            })}
          <ProceduralStrip items={proceduralItems} />
        </div>
      )}
    </div>
  )
}
