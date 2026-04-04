'use client'

import { useState } from 'react'
import * as Collapsible from '@radix-ui/react-collapsible'
import type { AgendaItemWithMotions, ThemeNarrative } from '@/lib/types'
import type { Significance } from '@/lib/significance'
import { getVoteTallySummary, didSplitVotePass } from '@/lib/significance'
import { agendaItemPath } from '@/lib/format'
import CategoryBadge from './CategoryBadge'
import TopicLabel from './TopicLabel'
import { useOperatorMode } from './OperatorModeProvider'

import Link from 'next/link'
import VoteBreakdown from './VoteBreakdown'
import ExpandableOfficialText from './ExpandableOfficialText'
import FormattedDescription from './FormattedDescription'

interface AgendaItemCardProps {
  item: AgendaItemWithMotions
  /** Visual significance level from topic board classification */
  significance?: Significance
  /** Number of campaign finance flags on this item */
  flagCount?: number
  onCategoryClick?: (category: string) => void
  selectedCategory?: string | null
  /** Amber accent for the #1 most-discussed item */
  mostDiscussed?: boolean
}

/** Card border classes — uniform styling, no colored left borders */
function getSignificanceStyles(): string {
  return 'border-slate-200'
}

/** Narrative copy scaled to engagement intensity (D6: narrative over numbers) */
function communityVoiceCopy(count: number): string {
  if (count >= 10) return 'This drew significant public input'
  return 'The public weighed in on this'
}

export default function AgendaItemCard({
  item,
  significance = 'standard',
  flagCount = 0,
  onCategoryClick,
  selectedCategory,
  mostDiscussed = false,
}: AgendaItemCardProps) {
  const { isOperator } = useOperatorMode()
  // Split/pulled items start expanded; consent starts collapsed
  const [expanded, setExpanded] = useState(
    significance === 'split' || significance === 'hero' || significance === 'pulled'
      ? true
      : !item.is_consent_calendar,
  )
  const [themesExpanded, setThemesExpanded] = useState(false)

  const hasMotions = item.motions.length > 0
  const hasDescription = item.description && item.description.length > 0
  const hasSummary = !!item.plain_language_summary
  const hasHeadline = !!item.summary_headline
  const voteTally = significance === 'split' || significance === 'hero'
    ? getVoteTallySummary(item)
    : null
  const votePassedSplit = voteTally ? didSplitVotePass(item) : false

  const significanceStyles = getSignificanceStyles()

  return (
    <div
      className={`bg-white rounded-lg border overflow-hidden ${mostDiscussed ? 'border-l-3 border-l-amber-500 border-slate-200' : significanceStyles}`}
    >
      <div className="p-4">
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <div>
              {mostDiscussed && (
                <span className="text-[11px] font-medium uppercase tracking-wide text-amber-600">
                  Most public comments
                </span>
              )}
              <h4 className={`font-medium leading-snug ${
                significance === 'split' || significance === 'hero' ? 'text-base' : 'text-sm'
              }`}>
                <span className="text-slate-900">
                  {hasHeadline ? item.summary_headline : item.title}
                </span>
              </h4>
              <div className="flex items-center gap-2 flex-wrap mt-1.5">
                {voteTally && (
                  <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                    votePassedSplit
                      ? 'bg-slate-100 text-civic-navy border border-slate-300'
                      : 'bg-red-50 text-vote-nay border border-red-200'
                  }`}>
                    {voteTally}
                  </span>
                )}
                {item.public_comment_count > 0 && (
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-civic-navy/10 text-civic-navy border border-civic-navy/20">
                    {item.public_comment_count} public {item.public_comment_count === 1 ? 'speaker' : 'speakers'}
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
            onClick={() => setExpanded(!expanded)}
            className="text-slate-400 shrink-0 text-lg hover:text-slate-600 p-1"
            aria-label={expanded ? 'Collapse details' : 'Expand details'}
          >
            {expanded ? '\u2212' : '+'}
          </button>
        </div>
      </div>

      {expanded && (hasDescription || hasMotions || hasSummary || item.public_comment_count > 0) && (
        <div className="px-4 pb-4 sm:ml-8">
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
                <FormattedDescription description={item.description} />
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
          {item.public_comment_count > 0 && (
            item.theme_narratives && item.theme_narratives.length > 0 ? (
              <div className="-mx-4 -mb-4 mt-4">
                <button
                  onClick={() => setThemesExpanded(!themesExpanded)}
                  className="group w-full flex items-center justify-between border-t border-slate-100 bg-gradient-to-r from-slate-50/80 to-transparent px-4 py-3.5 transition-all hover:from-civic-navy/[0.06] hover:to-transparent cursor-pointer"
                >
                  <span className="text-[11px] font-medium uppercase tracking-widest text-slate-400 group-hover:text-civic-navy transition-colors">
                    {communityVoiceCopy(item.public_comment_count)}
                  </span>
                  <svg
                    className={`h-3.5 w-3.5 text-slate-300 group-hover:text-civic-navy transition-transform ${themesExpanded ? 'rotate-180' : ''}`}
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
                </button>
                {themesExpanded && (
                  <InlineThemes
                    themes={item.theme_narratives}
                    spokenCount={item.spoken_comment_count ?? 0}
                    writtenCount={item.written_comment_count ?? 0}
                    commentSource={item.comment_source ?? null}
                    isOperator={isOperator}
                  />
                )}
              </div>
            ) : (
              <Link
                href={agendaItemPath(item.meeting_id, item.item_number)}
                className="group -mx-4 -mb-4 mt-4 flex items-center justify-between rounded-b-lg border-t border-slate-100 bg-gradient-to-r from-slate-50/80 to-transparent px-4 py-3.5 transition-all hover:from-civic-navy/[0.06] hover:to-transparent"
              >
                <span className="text-[11px] font-medium uppercase tracking-widest text-slate-400 group-hover:text-civic-navy transition-colors">
                  {communityVoiceCopy(item.public_comment_count)}
                </span>
                <svg
                  className="h-3.5 w-3.5 text-slate-300 group-hover:text-civic-navy group-hover:translate-x-0.5 transition-all"
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  aria-hidden="true"
                >
                  <path
                    fillRule="evenodd"
                    d="M3 10a.75.75 0 0 1 .75-.75h10.638L10.23 5.29a.75.75 0 1 1 1.04-1.08l5.5 5.25a.75.75 0 0 1 0 1.08l-5.5 5.25a.75.75 0 1 1-1.04-1.08l4.158-3.96H3.75A.75.75 0 0 1 3 10Z"
                    clipRule="evenodd"
                  />
                </svg>
              </Link>
            )
          )}
        </div>
      )}
    </div>
  )
}

// ── Inline Community Voice Themes ──────────────────────────────

/** Channel-aware count label: "5 spoke · 3 wrote" or "8 spoke" */
function channelLabel(spoken: number, written: number): string {
  if (spoken > 0 && written > 0) return `${spoken} spoke · ${written} wrote`
  if (written > 0) return `${written} wrote`
  return `${spoken} spoke`
}

/** Initial number of themes shown before "Show more" toggle */
const THEME_INITIAL_LIMIT = 5

function sourceLabel(source: string | null): string {
  switch (source) {
    case 'youtube_transcript': return 'meeting recording (KCRT)'
    case 'granicus_transcript': return 'meeting recording'
    case 'minutes': return 'official minutes'
    default: return 'meeting records'
  }
}

function InlineThemes({
  themes,
  spokenCount,
  writtenCount,
  commentSource,
  isOperator,
}: {
  themes: ThemeNarrative[]
  spokenCount: number
  writtenCount: number
  commentSource: string | null
  isOperator: boolean
}) {
  const [showAll, setShowAll] = useState(false)
  const total = spokenCount + writtenCount
  const hasOverflow = themes.length > THEME_INITIAL_LIMIT
  const visibleThemes = showAll ? themes : themes.slice(0, THEME_INITIAL_LIMIT)

  return (
    <div className="px-4 pb-4 pt-2">
      <p className="text-xs text-slate-500 mb-3">
        {total > 0 ? (
          <>{total} {total === 1 ? 'person' : 'people'} commented across {themes.length}{' '}
          {themes.length === 1 ? 'topic' : 'topics'}
          {' '}&mdash; {channelLabel(spokenCount, writtenCount)}</>
        ) : (
          <>{themes.length} {themes.length === 1 ? 'topic' : 'topics'} identified</>
        )}
      </p>
      <div className="space-y-2">
        {visibleThemes.map((tn) => (
          <InlineThemeCard key={tn.theme.slug} narrative={tn} isOperator={isOperator} />
        ))}
      </div>
      {hasOverflow && !showAll && (
        <button
          onClick={() => setShowAll(true)}
          className="mt-2 text-xs text-civic-navy-light hover:text-civic-navy transition-colors cursor-pointer"
        >
          Show {themes.length - THEME_INITIAL_LIMIT} more {themes.length - THEME_INITIAL_LIMIT === 1 ? 'topic' : 'topics'}
        </button>
      )}
      <p className="text-[10px] text-slate-400 mt-3 italic">
        Theme groupings and summaries are AI-generated from {sourceLabel(commentSource)}.
        {' '}Individual comments may touch multiple themes.
      </p>
    </div>
  )
}

/** Per-theme count: use assignment-based breakdown when available, fall back to narrative comment_count */
function themeCountLabel(tn: ThemeNarrative): string {
  const spoken = tn.spoken_count ?? 0
  const written = tn.written_count ?? 0
  if (spoken > 0 || written > 0) return channelLabel(spoken, written)
  if (tn.comment_count > 0) return `${tn.comment_count} ${tn.comment_count === 1 ? 'comment' : 'comments'}`
  return ''
}

/** Human-friendly label for the comment delivery method */
function methodLabel(method: string): string {
  switch (method) {
    case 'in_person': return 'In person'
    case 'zoom': return 'Via Zoom'
    case 'phone': return 'By phone'
    case 'email': return 'Email'
    case 'ecomment': return 'eComment'
    default: return method
  }
}

function InlineThemeCard({ narrative: tn, isOperator }: { narrative: ThemeNarrative; isOperator: boolean }) {
  const [open, setOpen] = useState(false)
  const [showComments, setShowComments] = useState(false)
  const countText = themeCountLabel(tn)
  const comments = tn.comments ?? []

  return (
    <Collapsible.Root open={open} onOpenChange={setOpen}>
      <Collapsible.Trigger asChild>
        <button className={`w-full flex items-center justify-between border border-slate-200 px-3 py-3 text-left transition-colors hover:border-slate-300 hover:bg-slate-50/50 cursor-pointer ${open ? 'rounded-t-md' : 'rounded-md'}`}>
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-sm font-medium text-civic-navy truncate">
              {tn.theme.label}
            </span>
            {countText && (
              <span className="text-xs text-slate-400 shrink-0">
                {countText}
              </span>
            )}
          </div>
          <svg
            className={`h-3 w-3 text-slate-400 shrink-0 ml-2 transition-transform ${open ? 'rotate-180' : ''}`}
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
        </button>
      </Collapsible.Trigger>
      <Collapsible.Content className="collapsible-content overflow-hidden">
        <div className="px-3 py-2.5 text-sm text-slate-600 leading-relaxed border-x border-b border-slate-200 rounded-b-md -mt-px">
          {tn.narrative}
          {tn.confidence < 0.9 && (
            <p className="text-xs text-amber-600 mt-1.5">
              Lower confidence grouping
            </p>
          )}
          {isOperator && comments.length > 0 && (
            <div className="mt-2 pt-2 border-t border-slate-100">
              <button
                onClick={(e) => { e.stopPropagation(); setShowComments(!showComments) }}
                className="text-[11px] text-civic-navy-light hover:text-civic-navy transition-colors cursor-pointer"
              >
                {showComments ? 'Hide' : 'Show'} {comments.length} {comments.length === 1 ? 'commenter' : 'commenters'}
              </button>
              {showComments && (
                <ul className="mt-1.5 space-y-0.5">
                  {comments.map((c, i) => (
                    <li key={i} className="text-xs text-slate-500 flex items-baseline gap-1.5">
                      <span className="font-medium text-slate-600">{c.speaker_name}</span>
                      <span className="text-slate-400">{methodLabel(c.method)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      </Collapsible.Content>
    </Collapsible.Root>
  )
}
