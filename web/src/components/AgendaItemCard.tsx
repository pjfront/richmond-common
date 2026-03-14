'use client'

import { useState } from 'react'
import type { AgendaItemWithMotions } from '@/lib/types'
import CategoryBadge from './CategoryBadge'
import { detectLocalIssues } from '@/lib/local-issues'

import VoteBreakdown from './VoteBreakdown'

interface AgendaItemCardProps {
  item: AgendaItemWithMotions
  onCategoryClick?: (category: string) => void
  selectedCategory?: string | null
}

export default function AgendaItemCard({ item, onCategoryClick, selectedCategory }: AgendaItemCardProps) {
  // Consent items start collapsed, regular items start expanded
  const [expanded, setExpanded] = useState(!item.is_consent_calendar)

  const hasMotions = item.motions.length > 0
  const hasDescription = item.description && item.description.length > 0
  const hasSummary = !!item.plain_language_summary
  const localIssues = detectLocalIssues(item.title)

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
              <CategoryBadge
                category={item.category}
                onClick={onCategoryClick}
                active={selectedCategory === item.category}
              />
              {localIssues.map(issue => (
                <span key={issue.id} className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${issue.color}`}>
                  {issue.label}
                </span>
              ))}
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

      {expanded && (hasDescription || hasMotions || hasSummary) && (
        <div className="px-4 pb-4 ml-8">
          {hasSummary && (
            <div className="bg-slate-50 border border-slate-200 rounded-md p-3 mb-3">
              <p className="text-xs font-medium text-slate-500 mb-1">In Plain English</p>
              <p className="text-sm text-slate-700 leading-relaxed">
                {item.plain_language_summary}
              </p>
              <p className="text-[10px] text-slate-400 mt-2">
                AI-generated summary. Source: official agenda documents.
              </p>
            </div>
          )}
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
