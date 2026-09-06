import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { AgendaItemWithMotions, MotionWithVotes, Vote } from './types'
import { didSplitVotePass, getCompactTally, getItemResultLabel, getOverallResult, getSignificance, getSplitVoteMargin, getVoteTallySummary, hasSplitVote } from './significance'
import { formalMotionResult, motionTallyLabel, recordedVoteCounts } from './vote-records'
import AgendaItemCard from '@/components/AgendaItemCard'
import HeroItem from '@/components/HeroItem'
import VoteRollCall from '@/components/VoteRollCall'
import { isSplitVote } from '@/components/VotingRecordTable'

vi.mock('@/components/ReportErrorLink', () => ({ default: () => <button>Report an error</button> }))

function vote(choice: string, index: number): Vote {
  return { id: `vote-${index}`, official_name: `Member ${index}`, vote_choice: choice, source: 'minutes' } as Vote
}
function motion(choices: string[], overrides: Partial<MotionWithVotes> = {}): MotionWithVotes {
  return { id: 'motion-1', motion_text: 'Approve the proposal', motion_type: 'original', source: 'minutes', result: 'passed', sequence_number: 1, votes: choices.map(vote), ...overrides } as MotionWithVotes
}
function item(motions: MotionWithVotes[], overrides: Partial<AgendaItemWithMotions> = {}): AgendaItemWithMotions {
  return { id: 'item-1', meeting_id: 'meeting-1', item_number: 'X.2', title: 'A council proposal', motions, public_comment_count: 0, is_consent_calendar: false, was_pulled_from_consent: false, ...overrides } as AgendaItemWithMotions
}

describe('motion-specific outcomes and recorded significance', () => {
  it('does not color a whole item failed after a failed motion to reject and a later adoption', () => {
    const record = item([
      motion(['aye', 'nay', 'nay'], { motion_text: 'Reject the proposal', result: 'failed' }),
      motion(['aye', 'aye', 'nay'], { id: 'motion-2', sequence_number: 2, motion_text: 'Adopt the proposal', result: 'passed' }),
    ])
    expect(getOverallResult(record)).toBe('mixed')
    expect(getItemResultLabel(record)).toBe('2 motions · see outcomes')
    expect(getCompactTally(record)).toBeNull()
    const html = renderToStaticMarkup(<AgendaItemCard item={record} />)
    expect(html).toContain('2 motions · see outcomes')
    expect(html).not.toContain('bg-red-50')
    expect(html).not.toContain('Failed')
  })

  it('does not call unanimous rejection or absent/recused votes a split', () => {
    for (const choices of [['nay', 'nay', 'nay'], ['yes', 'aye', 'absent', 'abstain', 'recused']]) {
      const record = item([motion(choices)])
      expect(hasSplitVote(record)).toBe(false)
      expect(getSplitVoteMargin(record)).toBeNull()
      expect(getVoteTallySummary(record)).toBeNull()
      expect(didSplitVotePass(record)).toBeNull()
    }
  })

  it('uses a recorded failure even when ayes outnumber nays, and never derives an unknown outcome', () => {
    expect(didSplitVotePass(item([motion(['aye', 'aye', 'aye', 'aye', 'nay', 'nay', 'nay'], { result: 'failed' })]))).toBe(false)
    expect(didSplitVotePass(item([motion(['aye', 'aye', 'nay'], { result: '' })]))).toBeNull()
    expect(didSplitVotePass(item([motion(['aye', 'aye', 'nay'], { result: 'passed', source: 'transcript' })]))).toBeNull()
  })

  it('keeps the displayed split tally and its result on the same motion', () => {
    const record = item([
      motion(['aye', 'aye', 'aye', 'aye', 'aye', 'aye', 'nay']),
      motion(['aye', 'aye', 'aye', 'nay', 'nay', 'nay', 'nay'], { id: 'motion-2', sequence_number: 2, result: 'failed' }),
    ])
    expect(getSplitVoteMargin(record)).toBe(1)
    expect(getVoteTallySummary(record)).toBe('3-4')
    expect(didSplitVotePass(record)).toBe(false)
  })

  it('does not infer consent approval and distinguishes amendments and procedural actions', () => {
    const consent = item([], { is_consent_calendar: true })
    expect(getSignificance(consent, [])).toBe('consent')
    expect(getOverallResult(consent)).toBe('none')
    expect(getItemResultLabel(consent)).toBeNull()
    expect(getSignificance(item([motion(['yes', 'no'])], { is_consent_calendar: true }), [])).toBe('split')
    expect(getItemResultLabel(item([motion([], { motion_type: 'friendly_amendment' })]))).toBe('Amendment passed')
    expect(getItemResultLabel(item([motion([], { motion_type: 'call_the_question' })]))).toBe('Motion to end debate passed')
    expect(getItemResultLabel(item([motion([], { result: 'unknown' })]))).toBe('Motion · outcome unverified')
  })

  it('separates abstentions, absences, recusals and unspecified records from yes/no votes', () => {
    const votes = ['yes', 'yea', 'no', 'noe', 'abstained', 'absent', 'recused', 'present'].map(vote)
    expect(recordedVoteCounts(votes)).toEqual({ aye: 2, nay: 2, abstain: 1, absent: 1, recused: 1, 'not-recorded': 1 })
    expect(motionTallyLabel(votes)).toBe('2 aye · 2 nay · 1 abstain · 1 absent · 1 recused · 1 unspecified')
    expect(formalMotionResult(motion([], { source: 'transcript' }))).toBe('unknown')
  })

  it('does not invent absence when an official has no vote row on another motion', () => {
    const first = motion(['aye'])
    const second = motion([], { id: 'motion-2', votes: [vote('recused', 1)], motion_type: 'friendly_amendment', result: '' })
    const html = renderToStaticMarkup(<VoteRollCall motions={[first, second]} />)
    expect(html).toContain('Member 0: Vote not recorded')
    expect(html).toContain('Member 1: Recused')
    expect(html).toContain('Amendment')
    expect(html).toContain('Outcome unverified')
    expect(html).not.toContain(': Absent')
  })

  it('describes public comments as observed records, not a measure of community opinion', () => {
    const html = renderToStaticMarkup(<HeroItem items={[item([], { public_comment_count: 12 })]} flags={[]} />)
    expect(html).toContain('12 public comments are recorded')
    expect(html).toContain('Most recorded public comments')
    expect(html).not.toContain('people spoke')
    expect(html).not.toContain('Most Contested')
  })

  it('does not let an old generated explainer assert passage beneath an unverified transcript outcome', () => {
    const html = renderToStaticMarkup(<VoteRollCall motions={[motion(['aye', 'aye', 'nay'], { source: 'transcript', vote_explainer: 'This proposal was approved and implemented.' })]} />)
    expect(html).toContain('Outcome unverified')
    expect(html).toContain('Tentative: auto-captioned recording')
    expect(html).not.toContain('approved and implemented')
  })

  it('does not treat an all-nay council-profile tally as a split merely because the nay flag is set', () => {
    const record = { id: 'vote-1', vote_choice: 'nay', meeting_id: 'meeting-1', meeting_date: '2026-03-17', meeting_type: 'regular', item_number: 'X.2', item_title: 'Proposal', category: null, motion_result: 'failed', is_consent_calendar: false, has_nay_votes: true }
    expect(isSplitVote({ ...record, vote_tally: '0-7' })).toBe(false)
    expect(isSplitVote({ ...record, vote_tally: 'Ayes (0), Noes (7)' })).toBe(false)
    expect(isSplitVote({ ...record, vote_tally: 'Ayes (4), Noes (3), Absent (0)' })).toBe(true)
    expect(isSplitVote({ ...record, vote_tally: 'Ayes (6), Noes (0), Absent (1)' })).toBe(false)
  })
})
