'use client'

import { useState, useMemo } from 'react'
import type { AgendaItemWithMotions } from '@/lib/types'
import AgendaItemCard from './AgendaItemCard'

interface ConsentCalendarSectionProps {
  items: AgendaItemWithMotions[]
  onCategoryClick?: (category: string) => void
  selectedCategory?: string | null
  /** When true, auto-expand the consent calendar (e.g. when a filter matches only consent items) */
  forceExpanded?: boolean
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
  const parsed: { title: string; amount: number }[] = []
  for (const item of items) {
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
}: ConsentCalendarSectionProps) {
  const [manualExpanded, setManualExpanded] = useState(false)
  const expanded = manualExpanded || forceExpanded

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
