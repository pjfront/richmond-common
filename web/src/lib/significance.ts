/**
 * Significance Detection — S14 A2
 *
 * Client-side classification of agenda items by objective signals.
 * Determines visual treatment (card sizing, prominence) in the topic board.
 *
 * All criteria are objective and AI-delegable — no editorial judgment.
 */

import type { AgendaItemWithMotions, ConflictFlag } from './types'

export type Significance =
  | 'hero'       // Selected as meeting hero (split vote by closest margin)
  | 'split'      // Any split vote (nays > 0)
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
  return item.motions.some(m => {
    if (m.votes.length === 0) return false
    const choices = new Set(m.votes.map(v => v.vote_choice.toLowerCase()))
    return choices.has('nay')
  })
}

/** Get the closest split vote margin for hero selection ranking */
export function getSplitVoteMargin(item: AgendaItemWithMotions): number | null {
  let closestMargin: number | null = null

  for (const motion of item.motions) {
    if (motion.votes.length === 0) continue
    const ayes = motion.votes.filter(v => v.vote_choice.toLowerCase() === 'aye').length
    const nays = motion.votes.filter(v => v.vote_choice.toLowerCase() === 'nay').length
    if (nays === 0) continue

    const margin = Math.abs(ayes - nays)
    if (closestMargin === null || margin < closestMargin) {
      closestMargin = margin
    }
  }

  return closestMargin
}

/** Determine significance level for an agenda item */
export function getSignificance(
  item: AgendaItemWithMotions,
  flags: ConflictFlag[],
): Significance {
  if (isProcedural(item)) return 'procedural'
  if (item.is_consent_calendar && !item.was_pulled_from_consent) return 'consent'
  if (hasSplitVote(item)) return 'split'
  if (item.was_pulled_from_consent) return 'pulled'
  if (flags.some(f => f.agenda_item_id === item.id)) return 'financial'
  return 'standard'
}

/** Get the vote tally summary for display (e.g., "4-3") */
export function getVoteTallySummary(item: AgendaItemWithMotions): string | null {
  for (const motion of item.motions) {
    if (motion.votes.length === 0) continue
    const ayes = motion.votes.filter(v => v.vote_choice.toLowerCase() === 'aye').length
    const nays = motion.votes.filter(v => v.vote_choice.toLowerCase() === 'nay').length
    if (nays > 0) return `${ayes}-${nays}`
  }
  return null
}

/** Did the split vote pass (ayes > nays)? */
export function didSplitVotePass(item: AgendaItemWithMotions): boolean {
  for (const motion of item.motions) {
    if (motion.votes.length === 0) continue
    const ayes = motion.votes.filter(v => v.vote_choice.toLowerCase() === 'aye').length
    const nays = motion.votes.filter(v => v.vote_choice.toLowerCase() === 'nay').length
    if (nays > 0) return ayes > nays
  }
  return true
}

/** Overall result across all motions with recorded votes */
export type OverallResult = 'passed' | 'failed' | 'mixed' | 'none'

export function getOverallResult(item: AgendaItemWithMotions): OverallResult {
  const voted = item.motions.filter(m => m.votes.length > 0)
  if (voted.length === 0) return 'none'
  const results = voted.map(m => m.result?.toLowerCase().trim() ?? '')
  const allPassed = results.every(r => r === 'passed' || r === 'approved')
  const anyFailed = results.some(r => r === 'failed' || r === 'denied')
  if (allPassed) return 'passed'
  if (anyFailed) return 'failed'
  return 'mixed'
}

/** Compact tally string for display (e.g., "7-0" or "3-4") */
export function getCompactTally(item: AgendaItemWithMotions): string | null {
  for (const motion of item.motions) {
    if (motion.votes.length === 0) continue
    const ayes = motion.votes.filter(v => v.vote_choice.toLowerCase() === 'aye').length
    const nays = motion.votes.filter(v => v.vote_choice.toLowerCase() === 'nay').length
    return `${ayes}-${nays}`
  }
  return null
}
