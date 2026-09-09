'use client'

import { useState } from 'react'
import type { AgendaItemWithMotions } from '@/lib/types'
import type { Significance } from '@/lib/significance'
import { getOverallResult, getCompactTally, getItemResultLabel } from '@/lib/significance'
import { agendaItemPath } from '@/lib/format'
import CategoryBadge from './CategoryBadge'
import TopicLabel from './TopicLabel'
import { useOperatorMode } from './OperatorModeProvider'

import Link from 'next/link'
import VoteRollCall from './VoteRollCall'
import ExpandableOfficialText from './ExpandableOfficialText'
import FormattedDescription from './FormattedDescription'
import { PlainLanguageAttribution } from './SourceAttribution'

interface AgendaItemCardProps {
  item: AgendaItemWithMotions
  significance?: Significance
  flagCount?: number
  onCategoryClick?: (category: string) => void
  selectedCategory?: string | null
  /** External control: force this item expanded (e.g., from ToC click) */
  forceExpanded?: boolean
  /** Brief highlight glow after scroll-to */
  highlighted?: boolean
}

/** Result label for collapsed row */
function resultLabel(item: AgendaItemWithMotions): { text: string; color: string } | null {
  const result = getOverallResult(item)
  const tally = getCompactTally(item)
  const label = getItemResultLabel(item)
  if (!label) return null
  const tallyStr = tally ? ` ${tally}` : ''
  if (result === 'passed') return { text: `${label}${tallyStr}`, color: 'text-vote-aye' }
  if (result === 'failed') return { text: `${label}${tallyStr}`, color: 'text-vote-nay' }
  return { text: label, color: 'text-slate-600' }
}

export default function AgendaItemCard({
  item,
  significance = 'standard',
  flagCount = 0,
  onCategoryClick,
  selectedCategory,
  forceExpanded = false,
  highlighted = false,
}: AgendaItemCardProps) {
  const { isOperator } = useOperatorMode()
  const [expanded, setExpanded] = useState(Boolean(forceExpanded))
  const [lastForceExpanded, setLastForceExpanded] = useState(forceExpanded)

  // Apply a new ToC request; a resident can still collapse the item afterward.
  if (forceExpanded !== lastForceExpanded) {
    setLastForceExpanded(forceExpanded)
    if (forceExpanded) setExpanded(true)
  }

  const hasMotions = item.motions.length > 0
  const hasDescription = item.description && item.description.length > 0
  const hasSummary = !!item.plain_language_summary
  const hasHeadline = !!item.summary_headline

  const headline = hasHeadline ? item.summary_headline! : item.title
  const result = resultLabel(item)

  // ── Collapsed state: card with metadata hints ──────────────
  if (!expanded) {
    const hasContent = hasSummary || hasDescription || hasMotions
    return (
      <div
        id={`agenda-item-${item.id}`}
        className={`group bg-white rounded-lg border px-4 py-3 transition-all duration-200 cursor-pointer border-slate-200 ${highlighted ? 'ring-2 ring-civic-navy/20' : ''} hover:border-slate-300 hover:shadow-sm`}
        onClick={() => setExpanded(true)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setExpanded(true) } }}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <span className="text-sm text-slate-800 font-medium leading-snug group-hover:text-civic-navy transition-colors line-clamp-2">
              {headline}
            </span>
            {/* Metadata hints — preview the richness inside */}
            <div className="flex items-center gap-1.5 flex-wrap mt-1.5">
              {result && (
                <span className={`inline-flex items-center px-1.5 py-px rounded text-[11px] font-medium ${
                  result.color === 'text-vote-aye'
                    ? 'bg-emerald-50 text-vote-aye'
                    : result.color === 'text-vote-nay'
                    ? 'bg-red-50 text-vote-nay'
                    : 'bg-slate-50 text-slate-500'
                }`}>
                  {result.text}
                </span>
              )}
              {item.topic_label && (
                <TopicLabel label={item.topic_label} compact />
              )}
            </div>
          </div>
          {/* Expand chevron */}
          {hasContent && (
            <svg
              className="h-4 w-4 text-slate-300 shrink-0 mt-0.5 group-hover:text-civic-navy transition-colors"
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 20 20"
              fill="currentColor"
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.168l3.71-3.938a.75.75 0 1 1 1.08 1.04l-4.25 4.5a.75.75 0 0 1-1.08 0l-4.25-4.5a.75.75 0 0 1 .02-1.06Z"
                clipRule="evenodd"
              />
            </svg>
          )}
        </div>
      </div>
    )
  }

  // ── Expanded state: full card ──────────────────────────────
  return (
    <div
      id={`agenda-item-${item.id}`}
      className={`bg-white rounded-lg border overflow-hidden transition-shadow duration-500 border-slate-200 ${highlighted ? 'ring-2 ring-civic-navy/20' : ''}`}
    >
      <div className="p-4">
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <div>
              <h4 className={`font-medium leading-snug ${
                significance === 'split' || significance === 'hero' ? 'text-base' : 'text-sm'
              }`}>
                <span className="text-slate-900">{headline}</span>
              </h4>
              <div className="flex items-center gap-2 flex-wrap mt-1.5">
                {result && (
                  <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                    result.color === 'text-vote-aye'
                      ? 'bg-emerald-50 text-vote-aye border border-emerald-200'
                      : result.color === 'text-vote-nay'
                      ? 'bg-red-50 text-vote-nay border border-red-200'
                      : 'bg-slate-50 text-slate-500 border border-slate-200'
                  }`}>
                    {result.text}
                  </span>
                )}
                {item.topic_label ? (
                  <TopicLabel label={item.topic_label} />
                ) : (
                  <CategoryBadge
                    category={item.category}
                    onClick={(cat) => { onCategoryClick?.(cat) }}
                    active={selectedCategory === item.category}
                  />
                )}
              </div>
            </div>
            {isOperator && flagCount > 0 && (
              <Link
                href={agendaItemPath(item.meeting_id, item.item_number)}
                className="block text-xs text-civic-amber mt-1 hover:underline"
              >
                {flagCount} campaign contribution {flagCount === 1 ? 'record' : 'records'} &rsaquo;
              </Link>
            )}
            {item.was_pulled_from_consent && (
              <p className="text-xs text-civic-amber mt-1 italic">
                Pulled from consent calendar for individual discussion
              </p>
            )}
          </div>
          <button
            onClick={() => setExpanded(false)}
            className="text-slate-400 shrink-0 text-lg hover:text-slate-600 p-1 cursor-pointer"
            aria-label="Collapse details"
          >
            {'\u2212'}
          </button>
        </div>
      </div>

      {(hasDescription || hasMotions || hasSummary) && (
        <div className="px-4 pb-4 sm:ml-8">
          {hasSummary && (
            <div className="bg-slate-50 border border-slate-200 rounded-md p-3 mb-3">
              <p className="text-xs font-medium text-slate-500 mb-1">In Plain English</p>
              <p className="text-sm text-slate-700 leading-relaxed">
                {item.plain_language_summary}
              </p>
              <p className="text-[10px] text-slate-400 mt-2">
                <PlainLanguageAttribution p={item.plain_language_summary_provenance ?? null} />
              </p>
            </div>
          )}
          {hasDescription && (
            hasSummary ? (
              <ExpandableOfficialText title={item.title} description={item.description} />
            ) : (
              <div className="mb-3">
                <p className="text-xs font-medium text-slate-500 mb-1">Official Agenda Text</p>
                <FormattedDescription description={item.description} />
              </div>
            )
          )}
          {item.motions.length > 0 && (
            <div className="mt-4 pt-1">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">Votes</p>
              <VoteRollCall motions={item.motions} />
            </div>
          )}
          {item.resolution_number && (
            <p className="text-xs text-slate-400 mt-2">
              Resolution {item.resolution_number}
            </p>
          )}

        </div>
      )}
      <div className="px-4 pb-4">
        <Link href={agendaItemPath(item.meeting_id, item.item_number)}
          className="inline-flex min-h-11 items-center text-sm text-civic-navy underline">
          Open this item’s source and available comment records →
        </Link>
      </div>
    </div>
  )
}
