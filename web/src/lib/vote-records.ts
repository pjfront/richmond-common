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

export interface IdentifiedVoteRecord {
  id?: string | null
  official_id?: string | null
  official_name?: string | null
  vote_choice: string
}
export type NormalizedMotionVote<T extends IdentifiedVoteRecord> = Omit<T, 'vote_choice'> & { vote_choice: RecordedChoice }

/** Official IDs outrank names. Never combine two IDs just because names match. */
export function recordedVoterKey(vote: IdentifiedVoteRecord, fallback: string): string {
  if (vote.official_id?.trim()) return `official:${vote.official_id}`
  const name = vote.official_name?.normalize('NFKC').trim().replace(/\s+/g, ' ').toLocaleLowerCase('en-US')
  return name ? `name:${name}` : vote.id ? `record:${vote.id}` : `unidentified:${fallback}`
}

/** Call on one motion only. A conflicting choice stays unresolved, even if a later row repeats one side. */
export function normalizeMotionVotes<T extends IdentifiedVoteRecord>(
  votes: T[],
  voterKey: (vote: T, index: number) => string = (vote, index) => recordedVoterKey(vote, String(index)),
): NormalizedMotionVote<T>[] {
  const records = new Map<string, NormalizedMotionVote<T>>()
  votes.forEach((vote, index) => {
    const key = voterKey(vote, index)
    const choice = normalizeRecordedChoice(vote.vote_choice)
    const existing = records.get(key)
    if (!existing) records.set(key, { ...vote, vote_choice: choice })
    else if (existing.vote_choice !== choice) records.set(key, { ...existing, vote_choice: 'not-recorded' })
  })
  return [...records.values()]
}

export function recordedVoteCounts(votes: IdentifiedVoteRecord[]): Record<RecordedChoice, number> {
  const counts: Record<RecordedChoice, number> = { aye: 0, nay: 0, abstain: 0, absent: 0, recused: 0, 'not-recorded': 0 }
  for (const vote of normalizeMotionVotes(votes)) counts[normalizeRecordedChoice(vote.vote_choice)] += 1
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

export function motionTallyLabel(votes: IdentifiedVoteRecord[]): string | null {
  if (votes.length === 0) return null
  const counts = recordedVoteCounts(votes)
  const parts = [`${counts.aye} aye`, `${counts.nay} nay`]
  for (const choice of ['abstain', 'absent', 'recused'] as const) {
    if (counts[choice] > 0) parts.push(`${counts[choice]} ${choice}`)
  }
  if (counts['not-recorded']) parts.push(`Incomplete: ${counts['not-recorded']} ${counts['not-recorded'] === 1 ? 'choice' : 'choices'} not established`)
  return parts.join(' · ')
}
