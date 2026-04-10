'use client'

import { useState, useMemo } from 'react'
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

/** Parse a financial_amount string like "$50,000" or "$1.2M" into a number, or null */
function parseFinancialAmount(raw: string | null): number | null {
  if (!raw) return null
  // Remove common text like "not to exceed", "up to", "approximately"
  const cleaned = raw.replace(/not to exceed|up to|approximately|approx\.?/gi, '').trim()
  // Match dollar amounts: $1,234,567 or $1.2M or $500K
  const match = cleaned.match(/\$\s*([\d,]+(?:\.\d+)?)\s*([MmKkBb])?/)
  if (!match) return null
  const num = parseFloat(match[1].replace(/,/g, ''))
  const suffix = (match[2] ?? '').toUpperCase()
  if (suffix === 'M') return num * 1_000_000
  if (suffix === 'K') return num * 1_000
  if (suffix === 'B') return num * 1_000_000_000
  return num
}

function formatDollars(amount: number): string {
  if (amount >= 1_000_000) {
    return `$${(amount / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`
  }
  if (amount >= 1_000) {
    return `$${Math.round(amount / 1_000).toLocaleString()}K`
  }
  return `$${Math.round(amount).toLocaleString()}`
}

interface FinancialSummary {
  total: number
  itemsWithAmounts: number
  topItems: { title: string; amount: number }[]
}

function computeFinancialSummary(items: AgendaItemWithMotions[]): FinancialSummary {
  // Detect parent wrapper items whose amounts double-count children.
  // If V.1 ($251K) has children V.1.a ($4.5K) and V.1.b ($246K), V.1 is
  // a parent whose amount is the sum — exclude it from the total.
  const itemNumbers = new Set(items.map(i => i.item_number).filter(Boolean))
  const parentNumbers = new Set<string>()
  for (const num of itemNumbers) {
    if (!num) continue
    // "V.1.a" → parent "V.1"
    const dotCount = (num.match(/\./g) ?? []).length
    if (dotCount >= 2) {
      parentNumbers.add(num.slice(0, num.lastIndexOf('.')))
    }
  }

  const parsed: { title: string; amount: number }[] = []
  for (const item of items) {
    // Skip parent wrappers — their children carry the real amounts
    if (item.item_number && parentNumbers.has(item.item_number)) continue
    const amount = parseFinancialAmount(item.financial_amount)
    if (amount !== null && amount > 0) {
      parsed.push({ title: item.title, amount })
    }
  }
  parsed.sort((a, b) => b.amount - a.amount)
  return {
    total: parsed.reduce((sum, p) => sum + p.amount, 0),
    itemsWithAmounts: parsed.length,
    topItems: parsed.slice(0, 3),
  }
}

/**
 * Consent calendar section — collapsible group of agenda items
 * with financial summary showing total dollar amounts.
 */
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

  const financial = useMemo(() => computeFinancialSummary(items), [items])

  if (items.length === 0) return null

  // Sort items so those with financial amounts appear first when expanded
  const sortedItems = useMemo(() => {
    return [...items].sort((a, b) => {
      const aAmt = parseFinancialAmount(a.financial_amount) ?? 0
      const bAmt = parseFinancialAmount(b.financial_amount) ?? 0
      return bAmt - aAmt
    })
  }, [items])

  return (
    <section className="mb-6">
      <button
        onClick={() => setManualExpanded(!expanded)}
        className="flex items-center gap-2 text-lg font-semibold text-slate-800 mb-2 hover:text-civic-navy transition-colors cursor-pointer"
      >
        Consent Calendar
        <span className="text-sm font-normal text-slate-400">
          ({items.length} {items.length === 1 ? 'item' : 'items'}
          {financial.total > 0 && ` · ${formatDollars(financial.total)} in contracts & approvals`})
        </span>
        <span className="text-sm text-slate-400">
          {expanded ? '\u2212' : '+'}
        </span>
      </button>

      {!expanded && (
        <div className="text-sm text-slate-500 space-y-1">
          <p>Approved as a group without individual discussion.</p>
          {financial.topItems.length > 0 && (
            <p className="text-xs text-slate-400">
              Biggest items:{' '}
              {financial.topItems
                .map((t) => `${formatDollars(t.amount)} ${truncateTitle(t.title)}`)
                .join(' · ')}
            </p>
          )}
        </div>
      )}

      {expanded && (
        <div className="space-y-3">
          {sortedItems.map(item => (
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
        </div>
      )}
    </section>
  )
}

/** Truncate a title to ~40 chars for the collapsed preview */
function truncateTitle(title: string): string {
  // Strip common prefixes like "APPROVE a contract with..." or "ADOPT a resolution..."
  const stripped = title
    .replace(/^(APPROVE|ADOPT|AUTHORIZE|ACCEPT|RECEIVE)\b\s*/i, '')
    .replace(/^(a |an |the )/i, '')
  if (stripped.length <= 40) return stripped
  return stripped.slice(0, 37) + '...'
}
