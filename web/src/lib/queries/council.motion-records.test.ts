import { beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ from: vi.fn(), rpc: vi.fn() }))
vi.mock('next/cache', () => ({ unstable_cache: (fn: unknown) => fn }))
vi.mock('./_shared', async (original) => ({ ...await original<typeof import('./_shared')>(), supabase: mocks }))
import { getDivergentMotions, getOfficialVotingRecord } from './council'

function builder(result: object) {
  const query = { select: vi.fn(), eq: vi.fn(), in: vi.fn(), order: vi.fn(), range: vi.fn(), limit: vi.fn(),
    then: (resolve: (value: object) => unknown) => Promise.resolve(result).then(resolve) }
  for (const fn of [query.select, query.eq, query.in, query.order, query.range, query.limit]) fn.mockReturnValue(query)
  return query
}
const officials = [{ id: 'a', name: 'Member A' }, { id: 'b', name: 'Member B' }, { id: 'new', name: 'Later Member' }]
const record = { motion_id: 'motion-1', motion_text: 'Reject the proposal', motion_result: 'failed', vote_tally: '3-4',
  meeting_id: 'meeting-1', meeting_date: '2024-01-09', agenda_item_id: 'item-1', agenda_item_title: 'Project application',
  agenda_item_number: 'H.1', category: 'housing', topic_label: null, is_procedural: false, official_id: 'a', official_name: 'Member A', vote_choice: 'aye' }
const no = { ...record, official_id: 'b', official_name: 'Member B', vote_choice: 'nay' }
const source = { id: 'motion-1', source: 'minutes', motion_type: 'original', agenda_item_id: 'item-1',
  agenda_items: { id: 'item-1', agenda_source_retired_at: null, meetings: { id: 'meeting-1', meeting_date: '2024-01-09',
    minutes_url: 'https://www.richmondca.gov/Archive.aspx?ADID=1', video_url: null, source_cancelled_at: null } } }
function setup(rows = [record, no], sourceData: object[] = [source]) {
  mocks.from.mockReturnValueOnce(builder({ data: officials, count: officials.length, error: null }))
    .mockReturnValueOnce(builder({ data: sourceData, count: sourceData.length, error: null }))
  mocks.rpc.mockReturnValueOnce(builder({ data: rows, count: rows.length, error: null }))
}

describe('bounded split-motion record query', () => {
  beforeEach(() => { mocks.from.mockReset(); mocks.rpc.mockReset() })
  it('keeps source identity and actual recorded choices without inventing absence or an overall result', async () => {
    setup([record, no, record])
    const result = await getDivergentMotions()
    expect(result.motions).toHaveLength(1)
    expect(result.motions[0]).toMatchObject({ source: 'minutes', source_tier: 1, source_url: source.agenda_items.meetings.minutes_url,
      motion_result: null, vote_tally: null, votes: { a: 'aye', b: 'nay' } })
    expect(result.motions[0].votes).not.toHaveProperty('new')
    expect(mocks.rpc).toHaveBeenCalledWith('get_divergent_motions_detail', expect.objectContaining({ p_official_ids: ['a', 'b', 'new'] }), { count: 'exact' })
  })
  it('preserves an explicit absence but keeps tentative transcript provenance distinct', async () => {
    setup([record, no, { ...record, official_id: 'new', vote_choice: 'absent' }], [{ ...source, source: 'transcript' }])
    expect((await getDivergentMotions()).motions[0]).toMatchObject({ source: 'transcript', source_tier: 2, votes: { new: 'absent' }, source_url: null })
  })
  it('refuses conflicting choices for the same member and motion', async () => {
    setup([record, no, { ...record, vote_choice: 'nay' }])
    await expect(getDivergentMotions()).rejects.toThrow('Split motion records is temporarily unavailable')
  })
  it.each([null, 5001, 3])('refuses missing, over-limit or incomplete count evidence (%s)', async count => {
    mocks.from.mockReturnValueOnce(builder({ data: officials, count: 3, error: null }))
    mocks.rpc.mockReturnValueOnce(builder({ data: [record, no], count, error: null }))
    if (count === 3) mocks.rpc.mockReturnValueOnce(builder({ data: [], count, error: null }))
    await expect(getDivergentMotions()).rejects.toThrow()
  })
  it('does not turn member lookup failure into an empty council', async () => {
    mocks.from.mockReturnValueOnce(builder({ data: null, count: null, error: new Error('offline') }))
    await expect(getDivergentMotions()).rejects.toThrow()
    expect(mocks.rpc).not.toHaveBeenCalled()
  })
  it('requires complete source metadata and discards cancelled or retired proceedings', async () => {
    setup([record, no], [])
    await expect(getDivergentMotions()).rejects.toThrow('Motion sources is temporarily unavailable')
    mocks.from.mockReset(); mocks.rpc.mockReset()
    setup([record, no], [{ ...source, agenda_items: { ...source.agenda_items, agenda_source_retired_at: '2026-09-06' } }])
    expect((await getDivergentMotions()).motions).toEqual([])
  })
  it('does not call all-nay records split even if the RPC supplied them', async () => {
    setup([{ ...record, vote_choice: 'nay' }, no])
    expect((await getDivergentMotions()).motions).toEqual([])
  })
})

describe('complete official voting record', () => {
  beforeEach(() => { mocks.from.mockReset(); mocks.rpc.mockReset() })
  it('reads past a lower server cap using actual offsets and stable identity ordering', async () => {
    const rows = Array.from({ length: 5 }, (_, i) => ({ ...record, id: `vote-${i}` }))
    const pages = [rows.slice(0, 2), rows.slice(2, 4), rows.slice(4)].map(data => builder({ data, count: 5, error: null }))
    for (const page of pages) mocks.rpc.mockReturnValueOnce(page)
    expect(await getOfficialVotingRecord('member-1')).toEqual(rows)
    expect(mocks.rpc).toHaveBeenCalledWith('get_official_voting_record', { p_official_id: 'member-1' }, { count: 'exact' })
    expect(pages.map(page => page.range.mock.calls[0])).toEqual([[0, 499], [2, 501], [4, 503]])
    for (const page of pages) expect(page.order.mock.calls).toEqual([['meeting_date', { ascending: false }], ['id']])
  })
  it.each([
    { data: null, count: null, error: { code: 'timeout' } },
    { data: [], count: null, error: null },
    { data: [], count: 1, error: null },
    { data: [{ id: 'repeat' }, { id: 'repeat' }], count: 2, error: null },
  ])('keeps unavailable and incomplete vote reads out of the summary', async response => {
    mocks.rpc.mockReturnValueOnce(builder(response))
    await expect(getOfficialVotingRecord('member-1')).rejects.toThrow('Official voting record is temporarily unavailable')
  })
  it('accepts a confirmed empty voting record', async () => {
    mocks.rpc.mockReturnValueOnce(builder({ data: [], count: 0, error: null }))
    expect(await getOfficialVotingRecord('member-1')).toEqual([])
  })
})
