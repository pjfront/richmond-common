import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import BioSummary from '@/components/BioSummary'
import { observedVoteSummary, uniqueObservedVoteRecords, officialMotionRecords, recordedDate } from './observed-vote-records'

const row = { id: 'vote-1', motion_id: 'motion-1', meeting_id: 'meeting-1', agenda_item_id: 'item-1', meeting_date: '2024-11-05', vote_choice: 'aye' }

describe('observed voting-record summaries', () => {
  it('counts the same displayed rows, preserving multiple motions but not repeated source IDs', () => {
    const rows = [row, { ...row }, { ...row, id: 'vote-2', motion_id: 'motion-2', vote_choice: 'nay' },
      { ...row, id: 'vote-3', meeting_id: 'meeting-2', meeting_date: '2025-01-07', vote_choice: 'absent' }]
    expect(observedVoteSummary(rows)).toEqual({ recordCount: 3, itemCount: 2, meetingCount: 2,
      firstDate: '2024-11-05', lastDate: '2025-01-07', undatedCount: 0 })
    expect(uniqueObservedVoteRecords(rows)).toHaveLength(3)
  })
  it('refuses conflicting records with the same identity', () => {
    expect(() => observedVoteSummary([row, { ...row, vote_choice: 'nay' }])).toThrow('conflicting')
    expect(() => observedVoteSummary([{ ...row, id: '' }])).toThrow('identity')
  })
  it('does not turn absence, abstention or recusal into attendance or policy support', () => {
    const rows = ['absent', 'abstain', 'recused'].map((vote_choice, index) => ({ ...row, id: String(index), vote_choice }))
    const summary = observedVoteSummary(rows)
    expect(summary.recordCount).toBe(3)
    expect(summary).not.toHaveProperty('attendanceRate')
    const html = renderToStaticMarkup(<BioSummary officialName="Example Member" votes={rows} />)
    expect(html).toContain('1 agenda item')
    expect(html).toContain('across 1 meeting')
    expect(html).not.toMatch(/100%|majority|attended|AI-generated|typical|approval/)
    expect(html).toContain('href="#votes"')
  })
  it('keeps empty coverage distinct from no votes and ignores unusable dates', () => {
    expect(recordedDate('2026-02-30')).toBeNull()
    expect(recordedDate('2026-09-06T00:00:00')).toBeNull()
    expect(observedVoteSummary([{ ...row, meeting_date: 'invalid' }])).toMatchObject({ firstDate: null, lastDate: null, undatedCount: 1 })
    const html = renderToStaticMarkup(<BioSummary officialName="Example" votes={[]} />)
    expect(html).toContain('does not establish that no votes were taken')
    expect(html).not.toContain('0%')
  })
  it('counts a single official’s repeated source rows as one motion, while preserving distinct motions', () => {
    const rows = [row, { ...row, id: 'repeat', vote_choice: 'yes' },
      { ...row, id: 'second', motion_id: 'motion-2', vote_choice: 'nay' }]
    expect(officialMotionRecords(rows).map(record => [record.motion_id, record.vote_choice])).toEqual([
      ['motion-1', 'aye'], ['motion-2', 'nay'],
    ])
    expect(officialMotionRecords([...rows, { ...row, id: 'conflict', vote_choice: 'nay' }, { ...row, id: 'again' }])[0].vote_choice).toBe('not-recorded')
    expect(() => officialMotionRecords([row, { ...row, id: 'bad', agenda_item_id: 'different-item' }])).toThrow('conflicting agenda')
  })
})
