import { beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ from: vi.fn(), rpc: vi.fn() }))
vi.mock('./_shared', async original => ({ ...await original<typeof import('./_shared')>(), supabase: { from: mocks.from, rpc: mocks.rpc } }))
vi.mock('./council', () => ({ getOfficials: vi.fn() }))
import { getMeetings, fetchMeetingCounts, applyMeetingCounts, getMeetingsWithCounts } from './meetings'
import { getCommissionMeetings } from './commissions'
import type { Meeting } from '../types'
function builder(data: object[] | null, count: number | null = data?.length ?? 0, error: object | null = null) {
  const q = { select: vi.fn(), eq: vi.fn(), in: vi.fn(), order: vi.fn(), range: vi.fn(),
    then: (resolve: (value: object) => unknown) => Promise.resolve({ data, count, error }).then(resolve) }
  for (const method of [q.select, q.eq, q.in, q.order, q.range]) method.mockReturnValue(q)
  return q
}
function fromPage(data: object[] | null, count: number | null = data?.length ?? 0, error: object | null = null) {
  const q = builder(data, count, error); mocks.from.mockReturnValueOnce(q); return q
}
function rpcPage(data: object[] | null, count: number | null = data?.length ?? 0, error: object | null = null) {
  const q = builder(data, count, error); mocks.rpc.mockReturnValueOnce(q); return q
}
const meeting = (id: string, stored = 999): Meeting => ({ id, meeting_date: '2026-06-02', agenda_item_count: stored } as Meeting)
const counts = (id: string, override = {}) => ({ meeting_id: id, agenda_item_count: 2, vote_count: 3,
  categories: [{ category: 'housing', count: 2 }], topic_labels: [{ label: 'Housing', count: 1 }], ...override })
beforeEach(() => { mocks.from.mockReset(); mocks.rpc.mockReset() })

describe('meeting index uses one complete count source', () => {
  it('paginates list and RPC by their actual returned rows even below the server page limit', async () => {
    const firstList = fromPage([meeting('one')], 2)
    const secondList = fromPage([meeting('two')], 2)
    const firstCounts = rpcPage([counts('one')], 2)
    const secondCounts = rpcPage([counts('two')], 2)
    const result = await getMeetingsWithCounts()
    expect(result).toHaveLength(2)
    expect(result[0]).toMatchObject({ agenda_item_count: 2, vote_count: 3, top_categories: [{ category: 'housing', count: 2 }], all_topic_labels: [{ label: 'Housing', count: 1 }] })
    expect(firstList.range).toHaveBeenCalledWith(0, 499)
    expect(secondList.range).toHaveBeenCalledWith(1, 500)
    expect(firstCounts.order).toHaveBeenCalledWith('meeting_id')
    expect(secondCounts.range).toHaveBeenCalledWith(1, 500)
    expect(mocks.rpc).toHaveBeenCalledWith('get_meeting_counts', { p_city_fips: '0660620' }, { count: 'exact' })
    expect(mocks.from.mock.calls).toEqual([['meetings'], ['meetings']])
  })
  it('throws on an RPC error without falling back to a partial agenda read or invented vote zeros', async () => {
    rpcPage(null, null, { code: '57014' })
    await expect(fetchMeetingCounts('0660620')).rejects.toThrow('temporarily unavailable')
    expect(mocks.from).not.toHaveBeenCalled()
  })
  it('requires an explicit source row even when the stored meeting count is zero', async () => {
    expect(() => applyMeetingCounts([meeting('missing', 0)], new Map())).toThrow('temporarily unavailable')
    rpcPage([counts('empty', { agenda_item_count: 0, vote_count: 0, categories: [], topic_labels: [] })])
    expect(applyMeetingCounts([meeting('empty', 999)], await fetchMeetingCounts('0660620'))).toMatchObject([
      { agenda_item_count: 0, vote_count: 0, top_categories: [], all_topic_labels: [] },
    ])
  })
  it('does not turn missing or failed list data into no meetings', async () => {
    fromPage(null, 0)
    await expect(getMeetings()).rejects.toThrow('temporarily unavailable')
    fromPage([], 0, { code: 'timeout' })
    await expect(getMeetings()).rejects.toThrow('temporarily unavailable')
    fromPage([], 0)
    expect(await getMeetings()).toEqual([])
  })
  it('rejects count drift, duplicate meeting identities, and incomplete RPC pages', async () => {
    rpcPage([counts('one')], 2); rpcPage([counts('two')], 3)
    await expect(fetchMeetingCounts('0660620')).rejects.toThrow('temporarily unavailable')
    rpcPage([counts('one')], 2); rpcPage([counts('one')], 2)
    await expect(fetchMeetingCounts('0660620')).rejects.toThrow('temporarily unavailable')
    rpcPage([counts('one')], 2); rpcPage([], 2)
    await expect(fetchMeetingCounts('0660620')).rejects.toThrow('temporarily unavailable')
    rpcPage(null, 0)
    await expect(fetchMeetingCounts('0660620')).rejects.toThrow('temporarily unavailable')
  })
  it.each([
    { agenda_item_count: null }, { vote_count: -1 }, { agenda_item_count: 1.5 }, { categories: null },
    { categories: [{ category: 'housing', count: 3 }] },
    { categories: [{ category: 'housing', count: 1 }, { category: 'housing', count: 1 }] },
    { topic_labels: [{ label: 'Housing', count: null }] },
  ])('rejects invalid source counts rather than coercing them: %j', async override => {
    rpcPage([counts('invalid', override)])
    await expect(fetchMeetingCounts('0660620')).rejects.toThrow('temporarily unavailable')
  })
})

describe('complete commission meeting reads', () => {
  it('keeps every exact linked body and applies the same count source', async () => {
    fromPage([{ id: 'body-one' }], 2)
    fromPage([{ id: 'body-two' }], 2)
    const query = fromPage([meeting('one')])
    rpcPage([counts('one')])
    expect(await getCommissionMeetings('commission-id')).toMatchObject([{ id: 'one', agenda_item_count: 2, vote_count: 3 }])
    expect(query.in).toHaveBeenCalledWith('body_id', ['body-one', 'body-two'])
    expect(query.select.mock.calls[0][1]).toEqual({ count: 'exact' })
  })
  it('returns no meetings only for an established empty body lookup', async () => {
    fromPage([], 0)
    expect(await getCommissionMeetings('commission-id')).toEqual([])
    expect(mocks.rpc).not.toHaveBeenCalled()
    fromPage(null, 0)
    await expect(getCommissionMeetings('commission-id')).rejects.toThrow('temporarily unavailable')
    fromPage([], 0, { code: 'timeout' })
    await expect(getCommissionMeetings('commission-id')).rejects.toThrow('temporarily unavailable')
  })
  it('propagates meeting read failures and missing count rows rather than returning empty or zero', async () => {
    fromPage([{ id: 'body' }]); fromPage(null, null, { code: 'timeout' }); rpcPage([counts('one')])
    await expect(getCommissionMeetings('commission-id')).rejects.toThrow('temporarily unavailable')
    fromPage([{ id: 'body' }]); fromPage([meeting('one')]); rpcPage([], 0)
    await expect(getCommissionMeetings('commission-id')).rejects.toThrow('temporarily unavailable')
  })
})
