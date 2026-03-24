/**
 * HeroItem — S14 A3
 *
 * Featured item at the top of the meeting page.
 * Selection is entirely objective (AI-delegable):
 *   1. Most public comments (min 3) — what the community cared about
 *   2. Split votes, ranked by closest margin (4-3 > 5-2 > 6-1)
 *   3. Pulled-from-consent items
 *   4. No qualifying item → renders nothing
 */

import Link from 'next/link'
import type { AgendaItemWithMotions, ConflictFlag } from '@/lib/types'
import { hasSplitVote, getSplitVoteMargin, getVoteTallySummary, didSplitVotePass } from '@/lib/significance'
import OperatorGate from './OperatorGate'

interface HeroItemProps {
  items: AgendaItemWithMotions[]
  flags: ConflictFlag[]
}

function selectHero(
  items: AgendaItemWithMotions[],
): AgendaItemWithMotions | null {
  // 1. Most public comments (min 3 to qualify)
  const commentedItems = items
    .filter(i => i.public_comment_count >= 3)
    .sort((a, b) => b.public_comment_count - a.public_comment_count)

  if (commentedItems.length > 0) return commentedItems[0]

  // 2. Split votes — closest margin first
  const splitItems = items
    .filter(i => hasSplitVote(i))
    .map(i => ({ item: i, margin: getSplitVoteMargin(i) ?? Infinity }))
    .sort((a, b) => a.margin - b.margin)

  if (splitItems.length > 0) return splitItems[0].item

  // 3. Pulled from consent
  const pulled = items.find(i => i.was_pulled_from_consent)
  if (pulled) return pulled

  return null
}

function buildNarrative(item: AgendaItemWithMotions): string {
  const parts: string[] = []

  if (item.public_comment_count > 0) {
    parts.push(
      `${item.public_comment_count} community ${item.public_comment_count === 1 ? 'member' : 'members'} commented on this item.`
    )
  }

  const tally = getVoteTallySummary(item)
  if (tally) {
    parts.push(`Council voted ${tally}.`)
  }

  if (parts.length > 0) return parts.join(' ')

  if (item.was_pulled_from_consent) {
    return 'This item was pulled from the consent calendar for individual discussion.'
  }

  return ''
}

function getHeroLabel(item: AgendaItemWithMotions): string {
  if (item.public_comment_count >= 3) return 'Most Discussed Item'
  if (hasSplitVote(item)) return 'Most Contested Item'
  if (item.was_pulled_from_consent) return 'Pulled from Consent'
  return 'Notable Item'
}

export default function HeroItem({ items, flags }: HeroItemProps) {
  const hero = selectHero(items)
  if (!hero) return null

  const narrative = buildNarrative(hero)
  const tally = getVoteTallySummary(hero)
  const passed = didSplitVotePass(hero)
  const label = getHeroLabel(hero)

  return (
    <div className="bg-gradient-to-r from-civic-navy/5 to-transparent border border-civic-navy/20 rounded-lg p-5 mb-6">
      <p className="text-xs font-medium text-civic-navy-light uppercase tracking-wide mb-2">
        {label}
      </p>
      <h3 className="text-lg font-semibold text-civic-navy leading-snug">
        {hero.summary_headline ?? hero.title}
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
        {hero.public_comment_count > 0 && (
          <span className="inline-flex items-center px-2.5 py-1 rounded text-sm font-bold bg-civic-navy/10 text-civic-navy border border-civic-navy/20">
            {hero.public_comment_count} {hero.public_comment_count === 1 ? 'comment' : 'comments'}
          </span>
        )}
        {tally && (
          <span className={`inline-flex items-center px-2.5 py-1 rounded text-sm font-bold ${
            passed
              ? 'bg-slate-100 text-civic-navy border border-slate-300'
              : 'bg-red-50 text-vote-nay border border-red-200'
          }`}>
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
