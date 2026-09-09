import { beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ snapshot: vi.fn(), from: vi.fn() }))
vi.mock('./agenda-metadata', () => ({ getAgendaMetadata: mocks.snapshot }))
vi.mock('./_shared', () => ({ supabase: { from: mocks.from }, RICHMOND_FIPS: '0660620' }))
import { getTopicCounts, getPromotedTopics } from './topics'
const topic = (label: string, count: number, meetings: number, date = '2026-09-03') => ({
  topic_label: label, item_count: count, meeting_count: meetings, latest_meeting_date: date,
})
describe('topic recurrence shares the meeting agenda snapshot', () => {
  beforeEach(() => { vi.clearAllMocks(); mocks.snapshot.mockReset() })
  it('uses the same source totals and meeting identities for all and promoted topics', async () => {
    mocks.snapshot.mockResolvedValue({ meetings: [], topics: [topic('Housing', 5, 3), topic('One meeting', 8, 1)] })
    expect(await getTopicCounts()).toEqual([
      { topic_label: 'One meeting', item_count: 8, latest_meeting_date: '2026-09-03' },
      { topic_label: 'Housing', item_count: 5, latest_meeting_date: '2026-09-03' },
    ])
    expect(await getPromotedTopics()).toEqual([{ label: 'Housing', slug: 'housing', item_count: 5, meeting_count: 3, latest_meeting_date: '2026-09-03' }])
    expect(mocks.snapshot).toHaveBeenCalledWith('0660620')
    expect(mocks.from).not.toHaveBeenCalled()
  })
  it('preserves explicit caller thresholds, city identity and latest-date ordering', async () => {
    mocks.snapshot.mockResolvedValue({ meetings: [], topics: [topic('Older', 6, 3, '2026-08-01'), topic('Newer', 6, 4)] })
    expect((await getPromotedTopics(6, 3, 'other-city')).map(row => row.label)).toEqual(['Newer', 'Older'])
    expect(mocks.snapshot).toHaveBeenCalledWith('other-city')
  })
  it.each([getTopicCounts, getPromotedTopics])('propagates incomplete shared reads and preserves real empty results', async read => {
    mocks.snapshot.mockRejectedValueOnce(new Error('Agenda metadata unavailable'))
    await expect(read()).rejects.toThrow('unavailable')
    mocks.snapshot.mockResolvedValueOnce({ meetings: [], topics: [] })
    expect(await read()).toEqual([])
  })
})
