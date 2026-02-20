'use client'

import { useState } from 'react'
import type { AgendaItemWithMotions } from '@/lib/types'
import CategoryBadge from './CategoryBadge'
import VoteBreakdown from './VoteBreakdown'

export default function AgendaItemCard({ item }: { item: AgendaItemWithMotions }) {
  // Consent items start collapsed, regular items start expanded
  const [expanded, setExpanded] = useState(!item.is_consent_calendar)

  const hasMotions = item.motions.length > 0
  const hasDescription = item.description && item.description.length > 0

  return (
    <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left p-4 hover:bg-slate-50 transition-colors"
      >
        <div className="flex items-start gap-3">
          <span className="text-xs font-mono text-slate-400 mt-1 shrink-0">
            {item.item_number}
          </span>
          <div className="flex-1 min-w-0">
            <div className="flex items-start gap-2 flex-wrap">
              <h4 className="font-medium text-slate-900 text-sm leading-snug">
                {item.title}
              </h4>
              <CategoryBadge category={item.category} />
            </div>
            {item.financial_amount && (
              <p className="text-sm text-civic-amber font-medium mt-1">
                {item.financial_amount}
              </p>
            )}
          </div>
          <span className="text-slate-400 shrink-0 text-lg">
            {expanded ? '\u2212' : '+'}
          </span>
        </div>
      </button>

      {expanded && (hasDescription || hasMotions) && (
        <div className="px-4 pb-4 ml-8">
          {hasDescription && (
            <p className="text-sm text-slate-600 leading-relaxed">
              {item.description}
            </p>
          )}
          {item.motions.map((motion) => (
            <VoteBreakdown key={motion.id} motion={motion} />
          ))}
          {item.resolution_number && (
            <p className="text-xs text-slate-400 mt-2">
              Resolution {item.resolution_number}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
