'use client'

import { useState, useMemo } from 'react'
import AgendaItemCard from './AgendaItemCard'
import type { AgendaItemWithMotions } from '@/lib/types'

const PROCEDURAL = 'procedural'

interface MeetingAgendaSectionProps {
  items: AgendaItemWithMotions[]
}

function formatCategory(cat: string): string {
  return cat.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export default function MeetingAgendaSection({ items }: MeetingAgendaSectionProps) {
  const [showProcedural, setShowProcedural] = useState(false)
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)

  function handleCategoryClick(category: string) {
    setSelectedCategory((prev) => (prev === category ? null : category))
  }

  const { consentItems, regularItems, proceduralCount, visibleCount } = useMemo(() => {
    let visible = showProcedural
      ? items
      : items.filter((i) => i.category !== PROCEDURAL)

    if (selectedCategory) {
      visible = visible.filter((i) => i.category === selectedCategory)
    }

    return {
      consentItems: visible.filter((i) => i.is_consent_calendar),
      regularItems: visible.filter((i) => !i.is_consent_calendar),
      proceduralCount: items.filter((i) => i.category === PROCEDURAL).length,
      visibleCount: visible.length,
    }
  }, [items, showProcedural, selectedCategory])

  const substantiveCount = items.length - proceduralCount

  return (
    <>
      {/* Filter controls */}
      <div className="mb-4 text-sm text-slate-500 space-y-2">
        {/* Procedural toggle */}
        {proceduralCount > 0 && (
          <div>
            {showProcedural ? (
              <span>
                Showing all {items.length} items &middot;{' '}
                <button
                  onClick={() => setShowProcedural(false)}
                  className="text-civic-navy hover:underline"
                >
                  hide {proceduralCount} procedural
                </button>
              </span>
            ) : (
              <span>
                {substantiveCount} substantive items &middot;{' '}
                {proceduralCount} procedural hidden &middot;{' '}
                <button
                  onClick={() => setShowProcedural(true)}
                  className="text-civic-navy hover:underline"
                >
                  show
                </button>
              </span>
            )}
          </div>
        )}

        {/* Active category filter */}
        {selectedCategory && (
          <div className="flex items-center gap-2">
            <span>Filtered to</span>
            <span className="font-medium text-slate-700">
              {formatCategory(selectedCategory)}
            </span>
            <span>({visibleCount} items)</span>
            <span>&middot;</span>
            <button
              onClick={() => setSelectedCategory(null)}
              className="text-civic-navy hover:underline"
            >
              clear filter
            </button>
          </div>
        )}
      </div>

      {/* Consent Calendar */}
      {consentItems.length > 0 && (
        <section className="mb-8">
          <h2 className="text-xl font-semibold text-slate-800 mb-3">
            Consent Calendar ({consentItems.length} items)
          </h2>
          <p className="text-sm text-slate-500 mb-3">
            Items approved as a group. Click to expand individual items.
          </p>
          <div className="space-y-2">
            {consentItems.map((item) => (
              <AgendaItemCard
                key={item.id}
                item={item}
                onCategoryClick={handleCategoryClick}
                selectedCategory={selectedCategory}
              />
            ))}
          </div>
        </section>
      )}

      {/* Regular Agenda */}
      {regularItems.length > 0 && (
        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-3">
            Agenda Items ({regularItems.length})
          </h2>
          <div className="space-y-2">
            {regularItems.map((item) => (
              <AgendaItemCard
                key={item.id}
                item={item}
                onCategoryClick={handleCategoryClick}
                selectedCategory={selectedCategory}
              />
            ))}
          </div>
        </section>
      )}

      {/* Empty state when filter produces no results */}
      {consentItems.length === 0 && regularItems.length === 0 && selectedCategory && (
        <p className="text-sm text-slate-400 italic">
          No {formatCategory(selectedCategory)} items in this meeting.{' '}
          <button
            onClick={() => setSelectedCategory(null)}
            className="text-civic-navy hover:underline not-italic"
          >
            Clear filter
          </button>
        </p>
      )}
    </>
  )
}
