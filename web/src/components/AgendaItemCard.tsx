'use client'

import { useState } from 'react'
import type { AgendaItemWithMotions } from '@/lib/types'
import type { Significance } from '@/lib/significance'
import { getVoteTallySummary, didSplitVotePass } from '@/lib/significance'
import { agendaItemPath } from '@/lib/format'
import CategoryBadge from './CategoryBadge'
import TopicLabel from './TopicLabel'
import { useOperatorMode } from './OperatorModeProvider'
import { useRouter } from 'next/navigation'

import Link from 'next/link'
import VoteBreakdown from './VoteBreakdown'
import ExpandableOfficialText from './ExpandableOfficialText'

interface AgendaItemCardProps {
  item: AgendaItemWithMotions
  /** Visual significance level from topic board classification */
  significance?: Significance
  /** Number of campaign finance flags on this item */
  flagCount?: number
  onCategoryClick?: (category: string) => void
  selectedCategory?: string | null
}

/** Card border classes — uniform styling, no colored left borders */
function getSignificanceStyles(): string {
  return 'border-slate-200'
}

export default function AgendaItemCard({
  item,
  significance = 'standard',
  flagCount = 0,
  onCategoryClick,
  selectedCategory,
}: AgendaItemCardProps) {
  const { isOperator } = useOperatorMode()
  const router = useRouter()
  // Split/pulled items start expanded; consent starts collapsed
  const [expanded, setExpanded] = useState(
    significance === 'split' || significance === 'hero' || significance === 'pulled'
      ? true
      : !item.is_consent_calendar,
  )

  const hasMotions = item.motions.length > 0
  const hasDescription = item.description && item.description.length > 0
  const hasSummary = !!item.plain_language_summary
  const hasHeadline = !!item.summary_headline
  const voteTally = significance === 'split' || significance === 'hero'
    ? getVoteTallySummary(item)
    : null
  const votePassedSplit = voteTally ? didSplitVotePass(item) : false

  const significanceStyles = getSignificanceStyles()
  const itemHref = agendaItemPath(item.meeting_id, item.item_number)

  return (
    <div
      className={`bg-white rounded-lg border overflow-hidden ${significanceStyles} hover:border-civic-navy/30 transition-colors cursor-pointer`}
      onClick={() => router.push(itemHref)}
      role="link"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter') router.push(itemHref) }}
    >
      <div className="p-4">
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <div>
              <h4 className={`font-medium leading-snug ${
                significance === 'split' || significance === 'hero' ? 'text-base' : 'text-sm'
              }`}>
                <span className="text-slate-900">
                  {hasHeadline ? item.summary_headline : item.title}
                </span>
              </h4>
              <div className="flex items-center gap-2 flex-wrap mt-1.5">
                {voteTally && (
                  <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-bold ${
                    votePassedSplit
                      ? 'bg-slate-100 text-civic-navy border border-slate-300'
                      : 'bg-red-50 text-vote-nay border border-red-200'
                  }`}>
                    {voteTally}
                  </span>
                )}
                {item.public_comment_count > 0 && (
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-civic-navy/10 text-civic-navy border border-civic-navy/20">
                    {item.public_comment_count} {item.public_comment_count === 1 ? 'comment' : 'comments'}
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
            {item.financial_amount && (
              <p className="text-sm text-civic-amber font-medium mt-1">
                {item.financial_amount}
              </p>
            )}
            {isOperator && flagCount > 0 && (
              <Link
                href={`/influence/item/${item.id}`}
                className="block text-xs text-civic-amber mt-1 hover:underline"
                onClick={(e) => e.stopPropagation()}
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
            onClick={(e) => { e.stopPropagation(); setExpanded(!expanded) }}
            className="text-slate-400 shrink-0 text-lg hover:text-slate-600 p-1"
            aria-label={expanded ? 'Collapse details' : 'Expand details'}
          >
            {expanded ? '\u2212' : '+'}
          </button>
        </div>
      </div>

      {expanded && (hasDescription || hasMotions || hasSummary) && (
        <div className="px-4 pb-4 sm:ml-8" onClick={(e) => e.stopPropagation()}>
          {hasSummary && (
            <div className="bg-slate-50 border border-slate-200 rounded-md p-3 mb-3">
              <p className="text-xs font-medium text-slate-500 mb-1">In Plain English</p>
              <p className="text-sm text-slate-700 leading-relaxed">
                {item.plain_language_summary}
              </p>
              <p className="text-[10px] text-slate-400 mt-2">
                Auto-generated summary. Source: official agenda documents.
              </p>
            </div>
          )}
          {hasDescription && (
            hasSummary ? (
              <ExpandableOfficialText title={item.title} description={item.description} />
            ) : (
              <div className="mb-3">
                <p className="text-xs font-medium text-slate-500 mb-1">Official Agenda Text</p>
                <div className="text-sm text-slate-600 leading-relaxed whitespace-pre-line">
                  {item.description}
                </div>
              </div>
            )
          )}
          {item.motions.length > 0 && (
            <div className="mt-4 pt-1">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">Votes</p>
              {item.motions.map((motion) => (
                <VoteBreakdown key={motion.id} motion={motion} />
              ))}
            </div>
          )}
          {item.resolution_number && (
            <p className="text-xs text-slate-400 mt-2">
              Resolution {item.resolution_number}
            </p>
          )}
          <Link
            href={itemHref}
            className="inline-block text-sm text-civic-navy-light hover:text-civic-navy hover:underline mt-3"
          >
            View full item details &rsaquo;
          </Link>
        </div>
      )}
    </div>
  )
}
