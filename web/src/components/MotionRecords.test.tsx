import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { DivergentMotion } from '@/lib/types'
import VotingPatternsDashboard from '@/app/council/analytics/VotingPatternsDashboard'
import DivergentMotionsTable from './DivergentMotionsTable'
import VotingRecordTable from './VotingRecordTable'
const officials = [{ id: 'a', name: 'Member A' }, { id: 'b', name: 'Member B' }, { id: 'new', name: 'Later Member' }]
const motion: DivergentMotion = { motion_id: 'motion-1', motion_text: 'Reject the proposal', motion_result: 'failed', vote_tally: '3-4',
  meeting_id: 'meeting-1', meeting_date: '2024-01-09', agenda_item_id: 'item-1', agenda_item_title: 'Project application',
  agenda_item_number: 'H.1', category: 'housing', topic_label: null, is_procedural: false, votes: { a: 'aye', b: 'nay' },
  source: 'transcript', source_url: 'https://www.youtube.com/watch?v=example', source_tier: 2 }
describe('public motion records', () => {
  it('shows the action and recorded choices without arbitrary result or invented missing members', () => {
    const html = renderToStaticMarkup(<DivergentMotionsTable motions={[motion]} officials={officials} />)
    expect(html).toContain('Reject the proposal')
    expect(html).toContain('Tentative transcript extraction')
    expect(html).not.toContain('Later Member')
    expect(html).not.toMatch(/Failed|Result:|Recorded absent|3-4/)
    expect(html).toContain('href="https://www.youtube.com/watch?v=example"')
  })
  it('uses one dated record set and removes the percentage matrix and unmeasured majority claims', () => {
    const html = renderToStaticMarkup(<VotingPatternsDashboard motions={[motion]} motionOfficials={officials} />)
    expect(html).toContain('1 of 1 motion records shown')
    expect(html).toContain('dateTime="2024-01-09"')
    expect(html).toContain('Missing choices do not establish absence')
    expect(html).not.toMatch(/percent|agreement|majority|Last updated|square|running out the clock/i)
    expect(html).toContain('min-h-11')
  })
  it('does not publish an unqualified profile outcome or rank AI speaker estimates', () => {
    const html = renderToStaticMarkup(<VotingRecordTable votes={[{ id: 'vote-1', vote_choice: 'aye',
      meeting_id: 'meeting-1', agenda_item_id: 'item-1', meeting_date: '2024-01-09', meeting_type: 'regular',
      item_number: 'H.1', item_title: 'Project application', motion_text: 'Reject the proposal', category: null,
      public_comment_count: 987, motion_result: 'passed', is_consent_calendar: false }]} />)
    expect(html).toContain('Reject the proposal')
    expect(html).not.toMatch(/987|Most discussed|Motion result|By result|passed/)
    expect(html).toContain('href="/meetings/meeting-1/items/h.1"')
  })
  it('shows two distinct motions rather than four repeated vote-source rows', () => {
    const vote = { id: 'vote-1', motion_id: 'motion-1', vote_choice: 'aye', meeting_id: 'meeting-1', agenda_item_id: 'item-1',
      meeting_date: '2024-01-09', meeting_type: 'regular', item_number: 'H.1', item_title: 'Project application',
      motion_text: 'Reject the proposal', category: null, motion_result: 'failed', is_consent_calendar: false }
    const html = renderToStaticMarkup(<VotingRecordTable votes={[vote, { ...vote, id: 'repeat' },
      { ...vote, id: 'conflicting', vote_choice: 'nay' },
      { ...vote, id: 'second', motion_id: 'motion-2', motion_text: 'Adopt the proposal' }]} />)
    expect(html).toContain('(2 motions)')
    expect(html).not.toContain('(4 motions)')
    expect(html).toContain('Choice not established')
    expect(html).toContain('Adopt the proposal')
  })
})
