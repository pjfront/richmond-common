'use client'

import { useState, useMemo } from 'react'
import CategoryBadge from './CategoryBadge'

interface CategoryCount {
  category: string
  count: number
}

interface TopicOverviewProps {
  categories: CategoryCount[]
  onCategoryClick?: (category: string) => void
  selectedCategory?: string | null
}

const PROCEDURAL = 'procedural'

export default function TopicOverview({ categories, onCategoryClick, selectedCategory }: TopicOverviewProps) {
  const [showProcedural, setShowProcedural] = useState(false)

  const { visible, proceduralCount, substantiveCount } = useMemo(() => {
    const procedural = categories.filter((c) => c.category === PROCEDURAL)
    const substantive = categories.filter((c) => c.category !== PROCEDURAL)
    const pCount = procedural.reduce((sum, c) => sum + c.count, 0)
    const sCount = substantive.reduce((sum, c) => sum + c.count, 0)

    return {
      visible: showProcedural ? categories : substantive,
      proceduralCount: pCount,
      substantiveCount: sCount,
    }
  }, [categories, showProcedural])

  const sorted = useMemo(
    () => [...visible].sort((a, b) => b.count - a.count),
    [visible]
  )

  const totalVisible = sorted.reduce((sum, c) => sum + c.count, 0)

  if (categories.length === 0) return null

  return (
    <section className="mb-8">
      <h2 className="text-xl font-semibold text-slate-800 mb-3">Topic Overview</h2>
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <div className="space-y-3">
          {sorted.map((cat) => {
            const pct = totalVisible > 0 ? Math.round((cat.count / totalVisible) * 100) : 0
            const isActive = selectedCategory === cat.category
            const rowClick = onCategoryClick ? () => onCategoryClick(cat.category) : undefined
            return (
              <div
                key={cat.category}
                role={rowClick ? 'button' : undefined}
                onClick={rowClick}
                className={`flex items-center gap-3 rounded-md px-1 -mx-1 ${
                  rowClick ? 'cursor-pointer hover:bg-slate-50' : ''
                } ${isActive ? 'bg-slate-50' : ''}`}
              >
                <div className="w-28 shrink-0">
                  <CategoryBadge
                    category={cat.category}
                    onClick={onCategoryClick}
                    active={isActive}
                  />
                </div>
                <div className="flex-1">
                  <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-civic-navy rounded-full"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
                <span className="text-sm text-slate-600 w-16 text-right">
                  {cat.count} ({pct}%)
                </span>
              </div>
            )
          })}
        </div>

        {/* Procedural toggle */}
        <div className="mt-3 text-sm text-slate-500">
          {showProcedural ? (
            <span>
              <strong>{substantiveCount + proceduralCount} total items</strong>
              {' '}&middot;{' '}
              <button
                onClick={() => setShowProcedural(false)}
                className="text-civic-navy hover:underline"
              >
                hide procedural
              </button>
            </span>
          ) : (
            <span>
              <strong>{substantiveCount} substantive items</strong>
              {proceduralCount > 0 && (
                <>
                  {' '}&middot; {proceduralCount} procedural hidden{' '}&middot;{' '}
                  <button
                    onClick={() => setShowProcedural(true)}
                    className="text-civic-navy hover:underline"
                  >
                    show
                  </button>
                </>
              )}
            </span>
          )}
        </div>
      </div>
    </section>
  )
}
