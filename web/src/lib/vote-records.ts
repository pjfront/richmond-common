import type { MotionWithVotes } from './types'

export type RecordedChoice = 'aye' | 'nay' | 'abstain' | 'absent' | 'recused' | 'not-recorded'
export function normalizeRecordedChoice(value: string): RecordedChoice {
  const choice = value.trim().toLowerCase()
  if (['aye', 'yes', 'yea', 'ayes'].includes(choice)) return 'aye'
  if (['nay', 'no', 'noe', 'noes', 'nays'].includes(choice)) return 'nay'
  if (['abstain', 'abstained', 'abstention'].includes(choice)) return 'abstain'
  if (choice === 'absent') return 'absent'
  if (['recused', 'recuse', 'recusal'].includes(choice)) return 'recused'
  return 'not-recorded'
}

export function recordedVoteCounts(votes: { vote_choice: string }[]): Record<RecordedChoice, number> {
  const counts: Record<RecordedChoice, number> = { aye: 0, nay: 0, abstain: 0, absent: 0, recused: 0, 'not-recorded': 0 }
  for (const vote of votes) counts[normalizeRecordedChoice(vote.vote_choice)] += 1
  return counts
}

/** A motion's recorded outcome is separate from its tally and the item's fate. */
export function formalMotionResult(motion: Pick<MotionWithVotes, 'source' | 'result'>): 'passed' | 'failed' | 'unknown' {
  if (motion.source !== 'minutes') return 'unknown'
  const result = motion.result?.trim().toLowerCase()
  if (['passed', 'approved', 'adopted', 'carried'].includes(result)) return 'passed'
  if (['failed', 'denied', 'lost'].includes(result)) return 'failed'
  return 'unknown'
}

export function motionKindLabel(motion: Pick<MotionWithVotes, 'motion_type'>): string {
  const labels: Record<string, string> = {
    original: 'Motion', substitute: 'Substitute motion', friendly_amendment: 'Amendment', amendment: 'Amendment',
    reconsider: 'Motion to reconsider', call_the_question: 'Motion to end debate', procedural: 'Procedural motion',
  }
  return labels[motion.motion_type?.trim().toLowerCase()] ?? 'Motion'
}

export function motionTallyLabel(votes: { vote_choice: string }[]): string | null {
  if (votes.length === 0) return null
  const counts = recordedVoteCounts(votes)
  const parts = [`${counts.aye} aye`, `${counts.nay} nay`]
  for (const choice of ['abstain', 'absent', 'recused', 'not-recorded'] as const) {
    if (counts[choice] > 0) parts.push(`${counts[choice]} ${choice === 'not-recorded' ? 'unspecified' : choice}`)
  }
  return parts.join(' · ')
}
