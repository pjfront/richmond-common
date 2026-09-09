import { beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ from: vi.fn(), rpc: vi.fn(), cacheOptions: [] as Array<{ key: string[]; options: unknown }> }))
vi.mock('next/cache', () => ({ unstable_cache: (fn: unknown, key: string[], options: unknown) => {
  mocks.cacheOptions.push({ key, options }); return fn
} }))
vi.mock('react', async original => ({ ...await original<typeof import('react')>(), cache: (fn: unknown) => fn }))
vi.mock('./_shared', async original => ({ ...await original<typeof import('./_shared')>(), supabase: mocks }))
import { getDivergentMotions, getOfficialVotingRecord } from './council'
import { SPLIT_MOTIONS_CACHE_TAG } from '../read-path-cache'

function builder(result: object) {
  const query = { select: vi.fn(), eq: vi.fn(), is: vi.fn(), in: vi.fn(), order: vi.fn(), range: vi.fn(), limit: vi.fn(),
    then: (resolve: (value: object) => unknown) => Promise.resolve(result).then(resolve) }
  for (const fn of [query.select, query.eq, query.is, query.in, query.order, query.range, query.limit]) fn.mockReturnValue(query)
  return query
}
const officials = [{ id: 'a', name: 'Member A' }, { id: 'b', name: 'Member B' }, { id: 'new', name: 'Later Member' }]
const record = { id: 'vote-a', motion_id: 'motion-1', official_id: 'a', vote_choice: 'aye' }
const no = { ...record, id: 'vote-b', official_id: 'b', vote_choice: 'nay' }
const source = { id: 'motion-1', source: 'minutes', motion_type: 'original', motion_text: 'Reject the proposal', agenda_item_id: 'item-1',
  agenda_items: { id: 'item-1', meeting_id: 'meeting-1', title: 'Project application', item_number: 'H.1', category: 'housing', topic_label: null,
    agenda_source_retired_at: null, meetings: { id: 'meeting-1', city_fips: '0660620', meeting_date: '2024-01-09',
      minutes_url: 'https://www.richmondca.gov/Archive.aspx?ADID=1', video_url: null, source_cancelled_at: null } } }
const candidate = { ...no, motions: source }
function page(data: object[] | null, count = data?.length ?? null, error: object | null = null) {
  const query = builder({ data, count, error }); mocks.from.mockReturnValueOnce(query); return query
}
function setup(rows = [record, no], sourceData: object[] = [source], candidates = [candidate]) {
  const members = page(officials)
  const discovery = page(candidates)
  const sources = page(sourceData)
  const votes = page(rows)
  return { members, discovery, sources, votes }
}

describe('bounded NAY-first split-motion query', () => {
  beforeEach(() => { mocks.from.mockReset(); mocks.rpc.mockReset() })
  it('keeps the current-member source cohort without broad RPC reads or invented absence/result', async () => {
    const queries = setup([record, no, { ...record, id: 'vote-a-repeat' }])
    const result = await getDivergentMotions()
    expect(result.motions).toHaveLength(1)
    expect(result.motions[0]).toMatchObject({ source: 'minutes', source_tier: 1, source_url: source.agenda_items.meetings.minutes_url,
      motion_text: 'Reject the proposal', meeting_date: '2024-01-09', agenda_item_id: 'item-1',
      motion_result: null, vote_tally: null, votes: { a: 'aye', b: 'nay' } })
    expect(result.motions[0].votes).not.toHaveProperty('new')
    expect(mocks.rpc).not.toHaveBeenCalled()
    expect(queries.discovery.eq.mock.calls).toContainEqual(['vote_choice', 'nay'])
    expect(queries.discovery.eq.mock.calls).toContainEqual(['motions.agenda_items.meetings.city_fips', '0660620'])
    expect(queries.discovery.is.mock.calls).toEqual([
      ['motions.agenda_items.agenda_source_retired_at', null], ['motions.agenda_items.meetings.source_cancelled_at', null],
    ])
    expect(queries.discovery.in).toHaveBeenCalledWith('official_id', ['a', 'b', 'new'])
    expect(queries.votes.in.mock.calls).toContainEqual(['motion_id', ['motion-1']])
    expect(queries.votes.in.mock.calls).toContainEqual(['official_id', ['a', 'b', 'new']])
    expect(mocks.cacheOptions).toContainEqual({ key: ['split-motion-records-v2'], options: { revalidate: 3600, tags: [SPLIT_MOTIONS_CACHE_TAG] } })
  })
  it('reads candidate and vote pages using actual offsets under a lower API cap', async () => {
    page(officials)
    const discovery = [page([candidate], 2), page([{ ...candidate, id: 'vote-new', official_id: 'new' }], 2)]
    page([source])
    const votes = [page([record, no], 3), page([{ ...no, id: 'vote-new', official_id: 'new' }], 3)]
    expect((await getDivergentMotions()).motions[0].votes).toEqual({ a: 'aye', b: 'nay', new: 'nay' })
    expect(discovery.map(q => q.range.mock.calls[0])).toEqual([[0, 499], [1, 500]])
    expect(votes.map(q => q.range.mock.calls[0])).toEqual([[0, 499], [2, 501]])
  })
  it('preserves explicit absence and tentative source provenance', async () => {
    setup([record, no, { ...record, id: 'vote-new', official_id: 'new', vote_choice: 'absent' }], [{ ...source, source: 'transcript' }])
    expect((await getDivergentMotions()).motions[0]).toMatchObject({ source: 'transcript', source_tier: 2, votes: { new: 'absent' }, source_url: null })
  })
  it.each([
    [record, no, { ...record, id: 'conflict', vote_choice: 'nay' }],
    [record, no, { ...record, id: 'unknown', vote_choice: 'not-recorded' }],
    [record, no, record],
    [record, no, { ...record, id: 'foreign-member', official_id: 'not-current' }],
    [record, no, { ...record, id: 'foreign-motion', motion_id: 'unselected' }],
    [record],
  ])('withholds conflicting, unrecognized, repeated, out-of-scope or changed vote records', async (...rows) => {
    setup(rows)
    await expect(getDivergentMotions()).rejects.toThrow('Split motion records is temporarily unavailable')
  })
  it.each([null, 5001, 2])('rejects incomplete candidate count evidence (%s)', async count => {
    page(officials); page([candidate], count)
    if (count === 2) page([], count)
    await expect(getDivergentMotions()).rejects.toThrow('Split motion candidates is temporarily unavailable')
  })
  it.each(['wrong-member', 'wrong-choice', 'wrong-motion', 'wrong-city', 'retired', 'cancelled', 'bad-date'])('rejects an invalid NAY candidate scope: %s', async problem => {
    const value = structuredClone(candidate)
    if (problem === 'wrong-member') value.official_id = 'former'
    if (problem === 'wrong-choice') value.vote_choice = 'aye'
    if (problem === 'wrong-motion') value.motion_id = 'other'
    if (problem === 'wrong-city') value.motions.agenda_items.meetings.city_fips = 'elsewhere'
    if (problem === 'retired') Object.assign(value.motions.agenda_items, { agenda_source_retired_at: '2026-09-06' })
    if (problem === 'cancelled') Object.assign(value.motions.agenda_items.meetings, { source_cancelled_at: '2026-09-06' })
    if (problem === 'bad-date') value.motions.agenda_items.meetings.meeting_date = ''
    page(officials); page([value])
    await expect(getDivergentMotions()).rejects.toThrow('Split motion candidates is temporarily unavailable')
  })
  it.each(['missing', 'changed-item', 'changed-date', 'foreign-city', 'repeated-id'])('requires complete matching source metadata: %s', async problem => {
    const changed = structuredClone(source)
    if (problem === 'changed-item') changed.agenda_item_id = 'other'
    if (problem === 'changed-date') changed.agenda_items.meetings.meeting_date = '2024-01-10'
    if (problem === 'foreign-city') changed.agenda_items.meetings.city_fips = 'elsewhere'
    setup([record, no], problem === 'missing' ? [] : problem === 'repeated-id' ? [changed, changed] : [changed])
    await expect(getDivergentMotions()).rejects.toThrow('Motion sources is temporarily unavailable')
  })
  it('does not turn a failed member read into an empty council, and a later successful read still works', async () => {
    page(null, null, new Error('offline'))
    await expect(getDivergentMotions()).rejects.toThrow('Council record members is temporarily unavailable')
    setup()
    expect((await getDivergentMotions()).motions).toHaveLength(1)
  })
  it('does not call an all-NAY motion a split and does not manufacture a discovery cohort', async () => {
    setup([{ ...record, vote_choice: 'nay' }, no])
    expect((await getDivergentMotions()).motions).toEqual([])
    page(officials); page([])
    expect(await getDivergentMotions()).toEqual({ motions: [], officials })
  })
  it('discards a proceeding explicitly retired between discovery and its source read', async () => {
    setup([record, no], [{ ...source, agenda_items: { ...source.agenda_items, agenda_source_retired_at: '2026-09-06' } }])
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
