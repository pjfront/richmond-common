/**
 * Significance Detection — S14 A2
 *
 * Client-side classification of agenda items by objective signals.
 * Determines visual treatment (card sizing, prominence) in the topic board.
 *
 * Signals describe the records available here, not citywide opinion or an
 * overall item outcome. Each motion retains its own result and purpose.
 */

import type { AgendaItemWithMotions, ConflictFlag } from './types'
import { formalMotionResult, motionKindLabel, recordedVoteCounts } from './vote-records'

export type Significance =
  | 'hero'       // Selected as meeting hero (split vote by closest margin)
  | 'split'      // A recorded motion has both ayes and nays
  | 'pulled'     // Pulled from consent calendar
  | 'financial'  // Has campaign finance records flagged
  | 'standard'   // Regular item, no special signals
  | 'consent'    // On consent calendar (not pulled)
  | 'procedural' // Call to order, adjournment, roll call

/** Procedural item patterns — these get minimal visual weight */
const PROCEDURAL_PATTERNS = [
  /^call to order/i,
  /^roll call/i,
  /^pledge of allegiance/i,
  /^adjournment/i,
  /^closed session/i,
  /^open forum/i,
  /^public comment/i,
  /^agenda review/i,
  /^consent calendar$/i,
]

export function isProcedural(item: AgendaItemWithMotions): boolean {
  if (item.category === 'procedural') return true
  return PROCEDURAL_PATTERNS.some(p => p.test(item.title.trim()))
}

/** Check if any motion on this item had a split vote */
export function hasSplitVote(item: AgendaItemWithMotions): boolean {
  return item.motions.some(motion => {
    const counts = recordedVoteCounts(motion.votes)
    return counts.aye > 0 && counts.nay > 0
  })
}

export function getClosestSplitMotion(item: AgendaItemWithMotions) {
  return item.motions.filter(motion => {
    const counts = recordedVoteCounts(motion.votes)
    return counts.aye > 0 && counts.nay > 0
  }).sort((a, b) => {
    const aVotes = recordedVoteCounts(a.votes)
    const bVotes = recordedVoteCounts(b.votes)
    return Math.abs(aVotes.aye - aVotes.nay) - Math.abs(bVotes.aye - bVotes.nay) || a.sequence_number - b.sequence_number
  })[0] ?? null
}

/** Get the closest split vote margin for hero selection ranking */
export function getSplitVoteMargin(item: AgendaItemWithMotions): number | null {
  const motion = getClosestSplitMotion(item)
  if (!motion) return null
  const counts = recordedVoteCounts(motion.votes)
  return Math.abs(counts.aye - counts.nay)
}

/** Determine significance level for an agenda item */
export function getSignificance(
  item: AgendaItemWithMotions,
  flags: ConflictFlag[],
): Significance {
  if (isProcedural(item)) return 'procedural'
  if (hasSplitVote(item)) return 'split'
  if (item.is_consent_calendar && !item.was_pulled_from_consent) return 'consent'
  if (item.was_pulled_from_consent) return 'pulled'
  if (flags.some(f => f.agenda_item_id === item.id)) return 'financial'
  return 'standard'
}

/** Get the vote tally summary for display (e.g., "4-3") */
export function getVoteTallySummary(item: AgendaItemWithMotions): string | null {
  const motion = getClosestSplitMotion(item)
  if (!motion) return null
  const counts = recordedVoteCounts(motion.votes)
  return `${counts.aye}-${counts.nay}`
}

/** Formal outcome of the exact motion whose split tally is displayed. */
export function didSplitVotePass(item: AgendaItemWithMotions): boolean | null {
  const motion = getClosestSplitMotion(item)
  if (!motion) return null
  const result = formalMotionResult(motion)
  return result === 'unknown' ? null : result === 'passed'
}

/** Legacy name: only a single motion can supply a compact result. Multiple
 * motions must be read individually; chronology alone does not settle an item. */
export type OverallResult = 'passed' | 'failed' | 'mixed' | 'unknown' | 'none'

export function getOverallResult(item: AgendaItemWithMotions): OverallResult {
  if (item.motions.length === 0) return 'none'
  if (item.motions.length > 1) return 'mixed'
  return formalMotionResult(item.motions[0])
}

export function getItemResultLabel(item: AgendaItemWithMotions): string | null {
  if (item.motions.length === 0) return null
  if (item.motions.length > 1) return `${item.motions.length} motions · see outcomes`
  const motion = item.motions[0]
  const result = formalMotionResult(motion)
  return result === 'unknown' ? `${motionKindLabel(motion)} · outcome unverified` : `${motionKindLabel(motion)} ${result}`
}

/** Compact tally string for display (e.g., "7-0" or "3-4") */
export function getCompactTally(item: AgendaItemWithMotions): string | null {
  if (item.motions.length !== 1) return null
  const counts = recordedVoteCounts(item.motions[0].votes)
  return counts.aye + counts.nay > 0 ? `${counts.aye}-${counts.nay}` : null
}
