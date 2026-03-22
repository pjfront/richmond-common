'use client'

import { useState } from 'react'
import Link from 'next/link'
import type { FinancialConnectionFlag } from '@/lib/types'
import { CampaignFinanceDisclaimer } from './InfluenceDisclaimer'
import ConfidenceBadge from './ConfidenceBadge'
import EntityTypeIndicator from './EntityTypeIndicator'
import CategoryBadge from './CategoryBadge'

/**
 * OfficialInfluenceSection — S14 D1
 *
 * Narrative-based influence section for council profiles. Replaces the
 * table-based FinancialConnectionsTable with agenda-item-grouped records
 * that link to /influence/item/[id] pages.
 *
 * Design principle: "contribution first, vote second" — same framing as
 * the item influence map (Phase C), applied at the official level.
 */

interface OfficialInfluenceSectionProps {
  officialName: string
  flags: FinancialConnectionFlag[]
}

interface AgendaItemGroup {
  agenda_item_id: string
  agenda_item_title: string
  agenda_item_number: string
  agenda_item_category: string | null
  meeting_id: string
  meeting_date: string
  vote_choice: string | null
  motion_result: string | null
  flags: FinancialConnectionFlag[]
}

function formatShortDate(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function groupFlagsByAgendaItem(flags: FinancialConnectionFlag[]): AgendaItemGroup[] {
  const groups = new Map<string, AgendaItemGroup>()

  for (const flag of flags) {
    const key = flag.agenda_item_id
    if (!groups.has(key)) {
      groups.set(key, {
        agenda_item_id: flag.agenda_item_id,
        agenda_item_title: flag.agenda_item_title,
        agenda_item_number: flag.agenda_item_number,
        agenda_item_category: flag.agenda_item_category,
        meeting_id: flag.meeting_id,
        meeting_date: flag.meeting_date,
        vote_choice: flag.vote_choice,
        motion_result: flag.motion_result,
        flags: [],
      })
    }
    groups.get(key)!.flags.push(flag)
  }

  // Sort by date descending, then by flag count descending
  return Array.from(groups.values()).sort((a, b) => {
    const dateCompare = b.meeting_date.localeCompare(a.meeting_date)
    if (dateCompare !== 0) return dateCompare
    return b.flags.length - a.flags.length
  })
}

const INITIAL_ITEMS = 5

export default function OfficialInfluenceSection({
  officialName,
  flags,
}: OfficialInfluenceSectionProps) {
  const [showAll, setShowAll] = useState(false)

  if (flags.length === 0) return null

  const groups = groupFlagsByAgendaItem(flags)
  const visibleGroups = showAll ? groups : groups.slice(0, INITIAL_ITEMS)
  const hiddenCount = groups.length - INITIAL_ITEMS

  return (
    <section className="mb-8">
      <div className="border-t border-slate-200 pt-8 mt-4">
        <h2 className="text-xl font-semibold text-slate-800 mb-2">
          Campaign Finance Context
          <span className="text-sm font-normal text-slate-500 ml-2">
            {flags.length} {flags.length === 1 ? 'record' : 'records'} across{' '}
            {groups.length} agenda {groups.length === 1 ? 'item' : 'items'}
          </span>
        </h2>

        <CampaignFinanceDisclaimer />

        <div className="space-y-3">
          {visibleGroups.map(group => (
            <AgendaItemCard
              key={group.agenda_item_id}
              group={group}
              officialName={officialName}
            />
          ))}
        </div>

        {/* Show more / show less */}
        {hiddenCount > 0 && (
          <div className="mt-4 text-center">
            <button
              onClick={() => setShowAll(!showAll)}
              className="text-sm text-civic-navy hover:underline transition-colors"
            >
              {showAll
                ? 'Show fewer items'
                : `Show ${hiddenCount} more agenda ${hiddenCount === 1 ? 'item' : 'items'}`
              }
            </button>
          </div>
        )}

        {/* Link to influence index */}
        <div className="mt-6 text-center">
          <Link
            href="/influence"
            className="text-xs text-civic-navy hover:underline"
          >
            View all officials on the influence map →
          </Link>
        </div>
      </div>
    </section>
  )
}

function AgendaItemCard({
  group,
  officialName,
}: {
  group: AgendaItemGroup
  officialName: string
}) {
  const voteLabel = group.vote_choice
    ? `${officialName} voted ${group.vote_choice.toLowerCase()}`
    : 'Vote not recorded'

  const voteColor = group.vote_choice?.toLowerCase() === 'aye'
    ? 'text-vote-aye'
    : group.vote_choice?.toLowerCase() === 'nay'
      ? 'text-vote-nay'
      : group.vote_choice?.toLowerCase() === 'abstain'
        ? 'text-vote-abstain'
        : 'text-slate-400'

  return (
    <Link
      href={`/influence/item/${group.agenda_item_id}`}
      className="block bg-white border border-slate-200 rounded-lg p-4 hover:bg-slate-50 hover:border-slate-300 transition-colors"
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          {/* Item header */}
          <div className="flex items-center gap-2 mb-1">
            <EntityTypeIndicator entityType="agenda_item" />
            {group.agenda_item_category && (
              <CategoryBadge category={group.agenda_item_category} />
            )}
          </div>

          <p className="text-sm font-medium text-slate-900 leading-snug">
            {group.agenda_item_title}
          </p>

          {/* Context line */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2 text-xs text-slate-500">
            <span>{formatShortDate(group.meeting_date)}</span>
            <span className={`font-medium ${voteColor}`}>{voteLabel}</span>
            <span>
              {group.flags.length} {group.flags.length === 1 ? 'connection' : 'connections'}
            </span>
          </div>

          {/* Confidence badges for this item's flags */}
          <div className="flex flex-wrap items-center gap-1.5 mt-2">
            {group.flags.slice(0, 3).map(f => (
              <ConfidenceBadge key={f.id} confidence={f.confidence} />
            ))}
            {group.flags.length > 3 && (
              <span className="text-[10px] text-slate-400">
                +{group.flags.length - 3} more
              </span>
            )}
          </div>
        </div>

        <span className="text-slate-400 text-sm ml-3 mt-1 shrink-0">→</span>
      </div>
    </Link>
  )
}
