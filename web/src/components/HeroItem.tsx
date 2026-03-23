/**
 * HeroItem — S14 A3
 *
 * Featured contested item at the top of the meeting page.
 * Selection is entirely objective (AI-delegable):
 *   1. Split votes, ranked by closest margin (4-3 > 5-2 > 6-1)
 *   2. Pulled-from-consent items
 *   3. Items with campaign finance records
 *   4. No qualifying item → renders nothing
 */

import Link from 'next/link'
import type { AgendaItemWithMotions, ConflictFlag } from '@/lib/types'
import { hasSplitVote, getSplitVoteMargin, getVoteTallySummary } from '@/lib/significance'
import OperatorGate from './OperatorGate'

interface HeroItemProps {
  items: AgendaItemWithMotions[]
  flags: ConflictFlag[]
}

function selectHero(
  items: AgendaItemWithMotions[],
  flags: ConflictFlag[],
): AgendaItemWithMotions | null {
  // 1. Split votes — closest margin first
  const splitItems = items
    .filter(i => hasSplitVote(i))
    .map(i => ({ item: i, margin: getSplitVoteMargin(i) ?? Infinity }))
    .sort((a, b) => a.margin - b.margin)

  if (splitItems.length > 0) return splitItems[0].item

  // 2. Pulled from consent
  const pulled = items.find(i => i.was_pulled_from_consent)
  if (pulled) return pulled

  // 3. Items with campaign finance flags
  const flaggedItemIds = new Set(flags.map(f => f.agenda_item_id).filter(Boolean))
  const flagged = items.find(i => flaggedItemIds.has(i.id))
  if (flagged) return flagged

  return null
}

function buildNarrative(item: AgendaItemWithMotions): string {
  const tally = getVoteTallySummary(item)

  if (tally) {
    return `Council voted ${tally} on this item.`
  }

  if (item.was_pulled_from_consent) {
    return 'This item was pulled from the consent calendar for individual discussion.'
  }

  return 'This item has associated campaign contribution records.'
}

export default function HeroItem({ items, flags }: HeroItemProps) {
  const hero = selectHero(items, flags)
  if (!hero) return null

  const narrative = buildNarrative(hero)
  const tally = getVoteTallySummary(hero)

  return (
    <div className="bg-gradient-to-r from-civic-navy/5 to-transparent border border-civic-navy/20 rounded-lg p-5 mb-6">
      <p className="text-xs font-medium text-civic-navy-light uppercase tracking-wide mb-2">
        Most Contested Item
      </p>
      <h3 className="text-lg font-semibold text-civic-navy leading-snug">
        {hero.title}
      </h3>
      <p className="text-sm text-slate-600 mt-2">
        {narrative}
      </p>
      {(hero.summary_headline || hero.plain_language_summary) && (
        <div className="mt-2">
          {hero.summary_headline && (
            <p className="text-sm font-medium text-slate-700">
              {hero.summary_headline}
            </p>
          )}
          {hero.plain_language_summary && (
            <p className={`text-sm text-slate-500 ${hero.summary_headline ? 'mt-1' : ''} italic`}>
              {hero.plain_language_summary}
            </p>
          )}
        </div>
      )}
      <div className="flex items-center gap-3 mt-3">
        {tally && (
          <span className="inline-flex items-center px-2.5 py-1 rounded text-sm font-bold bg-red-50 text-vote-nay border border-red-200">
            {tally}
          </span>
        )}
        {hero.financial_amount && (
          <span className="text-sm text-civic-amber font-medium">
            {hero.financial_amount}
          </span>
        )}
        <OperatorGate>
          {flags.some(f => f.agenda_item_id === hero.id) && (
            <Link
              href={`/influence/item/${hero.id}`}
              className="text-sm text-civic-navy hover:underline ml-auto"
            >
              View campaign finance context →
            </Link>
          )}
        </OperatorGate>
      </div>
    </div>
  )
}
