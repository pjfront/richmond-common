import { beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ from: vi.fn(), rpc: vi.fn(), snapshot: vi.fn() }))
vi.mock('./_shared', async original => ({ ...await original<typeof import('./_shared')>(), supabase: { from: mocks.from, rpc: mocks.rpc } }))
vi.mock('./council', () => ({ getOfficials: vi.fn() }))
vi.mock('./agenda-metadata', async original => ({ ...await original<typeof import('./agenda-metadata')>(), getAgendaMetadata: mocks.snapshot }))
vi.mock('next/cache', () => ({ unstable_cache: (fn: unknown) => fn }))
import { getMeetings, getMeetingsWithCounts } from './meetings'
import { getCommissionMeetings } from './commissions'
function page(data: object[] | null, count: number | null = data?.length ?? 0, error: object | null = null) {
  const q = { select: vi.fn(), eq: vi.fn(), in: vi.fn(), order: vi.fn(), range: vi.fn(),
    then: (resolve: (value: object) => unknown) => Promise.resolve({ data, count, error }).then(resolve) }
  for (const method of [q.select, q.eq, q.in, q.order, q.range]) method.mockReturnValue(q)
  mocks.from.mockReturnValueOnce(q); return q
}
const meeting = (id: string, body = 'body-one', count = 2) => ({ id, body_id: body, meeting_date: '2026-06-02',
  agenda_item_count: count, all_categories: count ? [{ category: 'housing', count }] : [],
  all_topic_labels: count ? [{ label: 'Housing', count }] : [] })
beforeEach(() => { vi.clearAllMocks(); mocks.from.mockReset(); mocks.snapshot.mockReset() })

describe('meeting index uses the shared agenda snapshot', () => {
  it('uses its inventory and derived counts without a second meeting list or vote RPC', async () => {
    mocks.snapshot.mockResolvedValue({ meetings: [meeting('one'), meeting('empty', 'body-two', 0)], topics: [] })
    expect(await getMeetingsWithCounts()).toMatchObject([
      { id: 'one', agenda_item_count: 2, top_categories: [{ category: 'housing', count: 2 }] },
      { id: 'empty', agenda_item_count: 0, top_categories: [], all_topic_labels: [] },
    ])
    expect(mocks.snapshot).toHaveBeenCalledWith('0660620')
    expect(mocks.from).not.toHaveBeenCalled(); expect(mocks.rpc).not.toHaveBeenCalled()
  })
  it('propagates a failed snapshot without fallback to stored counts or invented zeros', async () => {
    mocks.snapshot.mockRejectedValue(new Error('Agenda metadata temporarily unavailable'))
    await expect(getMeetingsWithCounts()).rejects.toThrow('temporarily unavailable')
    expect(mocks.from).not.toHaveBeenCalled(); expect(mocks.rpc).not.toHaveBeenCalled()
  })
  it('retains complete independent getMeetings reads for callers that need full metadata', async () => {
    page([{ id: 'one' }], 2); const later = page([{ id: 'two' }], 2)
    expect(await getMeetings()).toHaveLength(2)
    expect(later.range).toHaveBeenCalledWith(1, 500)
    page(null, 0); await expect(getMeetings()).rejects.toThrow('temporarily unavailable')
    page([], 0, { code: 'timeout' }); await expect(getMeetings()).rejects.toThrow('temporarily unavailable')
    page([], 0); expect(await getMeetings()).toEqual([])
  })
})

describe('commission meeting selection shares the checked inventory', () => {
  it('keeps every exact linked body and selects only its snapshot meetings', async () => {
    page([{ id: 'body-one' }], 2); const second = page([{ id: 'body-two' }], 2)
    mocks.snapshot.mockResolvedValue({ meetings: [meeting('one'), meeting('two', 'body-two', 0), meeting('other', 'body-other'), { ...meeting('unknown'), body_id: null }], topics: [] })
    expect((await getCommissionMeetings('commission-id')).map(row => row.id)).toEqual(['one', 'two'])
    expect(second.range).toHaveBeenCalledWith(1, 99)
    expect(mocks.from.mock.calls).toEqual([['bodies'], ['bodies']])
    expect(mocks.rpc).not.toHaveBeenCalled()
  })
  it('returns no meetings only for an established empty body lookup', async () => {
    page([], 0); expect(await getCommissionMeetings('commission-id')).toEqual([])
    expect(mocks.snapshot).not.toHaveBeenCalled()
    page(null, 0); await expect(getCommissionMeetings('commission-id')).rejects.toThrow('temporarily unavailable')
    page([], 0, { code: 'timeout' }); await expect(getCommissionMeetings('commission-id')).rejects.toThrow('temporarily unavailable')
  })
  it('propagates snapshot failure rather than returning an empty commission history', async () => {
    page([{ id: 'body-one' }]); mocks.snapshot.mockRejectedValue(new Error('Agenda metadata temporarily unavailable'))
    await expect(getCommissionMeetings('commission-id')).rejects.toThrow('temporarily unavailable')
  })
})
