'use client'

import { useState, useEffect } from 'react'
import * as Collapsible from '@radix-ui/react-collapsible'
import type { AgendaItemWithMotions, ThemeNarrative } from '@/lib/types'
import type { Significance } from '@/lib/significance'
import { getOverallResult, getCompactTally } from '@/lib/significance'
import { agendaItemPath } from '@/lib/format'
import CategoryBadge from './CategoryBadge'
import TopicLabel from './TopicLabel'
import { useOperatorMode } from './OperatorModeProvider'

import Link from 'next/link'
import VoteRollCall from './VoteRollCall'
import ExpandableOfficialText from './ExpandableOfficialText'
import FormattedDescription from './FormattedDescription'

interface AgendaItemCardProps {
  item: AgendaItemWithMotions
  significance?: Significance
  flagCount?: number
  onCategoryClick?: (category: string) => void
  selectedCategory?: string | null
  /** Amber accent for the #1 most-discussed item */
  mostDiscussed?: boolean
  /** External control: force this item expanded (e.g., from ToC click) */
  forceExpanded?: boolean
  /** Brief highlight glow after scroll-to */
  highlighted?: boolean
}

/** Narrative copy scaled to engagement intensity (D6: narrative over numbers) */
function communityVoiceCopy(count: number): string {
  if (count >= 10) return 'This drew significant public input'
  return 'The public weighed in on this'
}

/** Result label for collapsed row */
function resultLabel(item: AgendaItemWithMotions): { text: string; color: string } | null {
  const result = getOverallResult(item)
  const tally = getCompactTally(item)
  if (result === 'none') return null
  const tallyStr = tally ? ` ${tally}` : ''
  if (result === 'passed') return { text: `Passed${tallyStr}`, color: 'text-vote-aye' }
  if (result === 'failed') return { text: `Failed${tallyStr}`, color: 'text-vote-nay' }
  return { text: `Mixed${tallyStr}`, color: 'text-slate-500' }
}

export default function AgendaItemCard({
  item,
  significance = 'standard',
  flagCount = 0,
  onCategoryClick,
  selectedCategory,
  mostDiscussed = false,
  forceExpanded = false,
  highlighted = false,
}: AgendaItemCardProps) {
  const { isOperator } = useOperatorMode()
  const [expanded, setExpanded] = useState(false)
  const [themesExpanded, setThemesExpanded] = useState(false)

  // External expand control (from ToC click)
  useEffect(() => {
    if (forceExpanded) setExpanded(true)
  }, [forceExpanded])

  const hasMotions = item.motions.length > 0
  const hasDescription = item.description && item.description.length > 0
  const hasSummary = !!item.plain_language_summary
  const hasHeadline = !!item.summary_headline

  const headline = hasHeadline ? item.summary_headline! : item.title
  const result = resultLabel(item)

  // ── Collapsed state: card with metadata hints ──────────────
  if (!expanded) {
    const hasContent = hasSummary || hasDescription || hasMotions || item.public_comment_count > 0
    return (
      <div
        id={`agenda-item-${item.id}`}
        className={`group bg-white rounded-lg border px-4 py-3 transition-all duration-200 cursor-pointer ${
          mostDiscussed ? 'border-l-3 border-l-amber-500 border-slate-200' : 'border-slate-200'
        } ${highlighted ? 'ring-2 ring-civic-navy/20' : ''} hover:border-slate-300 hover:shadow-sm`}
        onClick={() => setExpanded(true)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setExpanded(true) } }}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            {mostDiscussed && (
              <span className="text-[10px] font-medium uppercase tracking-wide text-amber-600">
                Top
              </span>
            )}
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
              {item.public_comment_count > 0 && (
                <span className="inline-flex items-center px-1.5 py-px rounded text-[11px] font-medium bg-civic-navy/[0.08] text-civic-navy">
                  {item.public_comment_count} {item.public_comment_count === 1 ? 'speaker' : 'speakers'}
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
      className={`bg-white rounded-lg border overflow-hidden transition-shadow duration-500 ${
        mostDiscussed ? 'border-l-3 border-l-amber-500 border-slate-200' : 'border-slate-200'
      } ${highlighted ? 'ring-2 ring-civic-navy/20' : ''}`}
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
            {item.financial_amount &&
              !(hasHeadline && item.summary_headline!.includes('$')) && (
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
            onClick={() => setExpanded(false)}
            className="text-slate-400 shrink-0 text-lg hover:text-slate-600 p-1 cursor-pointer"
            aria-label="Collapse details"
          >
            {'\u2212'}
          </button>
        </div>
      </div>

      {(hasDescription || hasMotions || hasSummary || item.public_comment_count > 0) && (
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
              <VoteRollCall motions={item.motions} />
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
              <div className="-mx-4 -mb-4 mt-4 rounded-b-lg border-t border-slate-100 bg-gradient-to-r from-slate-50/80 to-transparent px-4 py-3.5">
                <span className="text-[11px] font-medium uppercase tracking-widest text-slate-400">
                  {communityVoiceCopy(item.public_comment_count)}
                </span>
                <p className="text-[10px] text-slate-400 mt-1">
                  Comment details will appear once meeting records are processed.
                </p>
              </div>
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
          {' '}({channelLabel(spokenCount, writtenCount)})</>
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
        Theme groupings and summaries are auto-generated from {sourceLabel(commentSource)}.
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
