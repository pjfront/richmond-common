'use client'

import type { AgendaItemWithMotions, ConflictFlag } from '@/lib/types'
import type { Significance } from '@/lib/significance'
import { formatCategory } from './CategoryBadge'
import AgendaItemCard from './AgendaItemCard'

interface CategorySectionProps {
  category: string
  items: AgendaItemWithMotions[]
  significanceMap: Map<string, Significance>
  flags: ConflictFlag[]
  onCategoryClick?: (category: string) => void
  selectedCategory?: string | null
}

export default function CategorySection({
  category,
  items,
  significanceMap,
  flags,
  onCategoryClick,
  selectedCategory,
}: CategorySectionProps) {
  if (items.length === 0) return null

  return (
    <section className="mb-6">
      <h3 className="text-lg font-semibold text-slate-800 mb-2 flex items-center gap-2">
        {formatCategory(category)}
        <span className="text-sm font-normal text-slate-400">
          ({items.length} {items.length === 1 ? 'item' : 'items'})
        </span>
      </h3>
      <div className="space-y-2">
        {items.map(item => {
          const significance = significanceMap.get(item.id) ?? 'standard'
          const itemFlags = flags.filter(f => f.agenda_item_id === item.id)
          return (
            <AgendaItemCard
              key={item.id}
              item={item}
              significance={significance}
              flagCount={itemFlags.length}
              onCategoryClick={onCategoryClick}
              selectedCategory={selectedCategory}
            />
          )
        })}
      </div>
    </section>
  )
}
