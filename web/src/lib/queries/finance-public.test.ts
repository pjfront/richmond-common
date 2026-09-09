import { beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ from: vi.fn() }))
vi.mock('next/cache', () => ({ unstable_cache: (fn: unknown) => fn }))
vi.mock('@/lib/supabase', () => ({ supabase: { from: mocks.from } }))
import { getPublicFinanceSnapshot, PUBLIC_FINANCE_SCOPE } from './finance-public'
function page(data: object[] | null, count: number | null = data?.length ?? 0, error: object | null = null) {
  const query = { select: vi.fn(), eq: vi.fn(), gte: vi.fn(), lte: vi.fn(), order: vi.fn(), range: vi.fn(), limit: vi.fn(),
    then: (resolve: (value: object) => unknown) => Promise.resolve({ data, count, error }).then(resolve) }
  for (const method of [query.select, query.eq, query.gte, query.lte, query.order, query.range, query.limit]) method.mockReturnValue(query)
  mocks.from.mockReturnValueOnce(query)
  return query
}
const row = { event_key: 'correction', scope_key: PUBLIC_FINANCE_SCOPE, amount: '-25.10', amount_kind: 'negative_adjustment', source_url: 'https://netfile.com/filing/1', source_urls: ['https://netfile.com/filing/1'], extracted_at: '2026-09-06T12:00:00Z' }

describe('complete public finance projection reads', () => {
  beforeEach(() => mocks.from.mockReset())
  it('preserves signed semantics and reads exact-count events and acquisition windows in the same scope', async () => {
    const events = page([row])
    const coverage = page([{ scope_key: PUBLIC_FINANCE_SCOPE, activity_from: '2026-01-01', activity_through: '2026-09-06' }])
    const result = await getPublicFinanceSnapshot()
    expect(result.events[0]).toEqual({ ...row, amount: -25.10 })
    expect(events.select.mock.calls[0][1]).toEqual({ count: 'exact' })
    expect(coverage.select.mock.calls[0][1]).toEqual({ count: 'exact' })
    expect(events.eq).toHaveBeenCalledWith('scope_key', PUBLIC_FINANCE_SCOPE)
    expect(coverage.eq).toHaveBeenCalledWith('scope_key', PUBLIC_FINANCE_SCOPE)
    expect(result.coverage[0].activity_through).toBe('2026-09-06')
    expect(result.truncated).toBe(false)
  })
  it('continues after a short server-capped page using the actual returned row count', async () => {
    const first = page([{ ...row, event_key: 'one' }], 3)
    const second = page([{ ...row, event_key: 'two' }], 3)
    const third = page([{ ...row, event_key: 'three' }], 3)
    page([])
    const result = await getPublicFinanceSnapshot()
    expect(result.events.map(entry => entry.event_key)).toEqual(['one', 'two', 'three'])
    expect(first.range).toHaveBeenCalledWith(0, 999)
    expect(second.range).toHaveBeenCalledWith(1, 1000)
    expect(third.range).toHaveBeenCalledWith(2, 1001)
    expect(result.truncated).toBe(false)
  })
  it('rejects missing counts, changing counts, duplicate keys and pages that end too soon', async () => {
    page([], null)
    await expect(getPublicFinanceSnapshot()).rejects.toThrow('count unavailable or changed')
    page([row], 2); page([{ ...row, event_key: 'two' }], 3)
    await expect(getPublicFinanceSnapshot()).rejects.toThrow('count unavailable or changed')
    page([row], 2); page([row], 2)
    await expect(getPublicFinanceSnapshot()).rejects.toThrow('identity was repeated')
    page([row], 2); page([], 2)
    await expect(getPublicFinanceSnapshot()).rejects.toThrow('page was incomplete')
  })
  it.each([{ amount_kind: null }, { amount: null }, { amount: 'NaN' }])('never turns invalid source/amount into zero: %j', async override => {
    page([{ ...row, ...override }])
    await expect(getPublicFinanceSnapshot()).rejects.toThrow('incomplete provenance or amount')
    expect(mocks.from).toHaveBeenCalledTimes(1)
  })
  it('throws if exact counts cannot be completed within the lower-cap page budget', async () => {
    for (let index = 0; index < 20; index++) page([{ ...row, event_key: `event-${index}` }], 21)
    await expect(getPublicFinanceSnapshot()).rejects.toThrow('page budget exhausted')
    expect(mocks.from).toHaveBeenCalledTimes(20)
  })
  it.each([5000, 5001])('marks only an actually incomplete bounded %i-record set as truncated', async count => {
    const queries = []
    for (let offset = 0; offset < 5000; offset += 1000) queries.push(page(Array.from({ length: 1000 }, (_, index) => ({ ...row, event_key: `event-${offset + index}` })), count))
    page([])
    const result = await getPublicFinanceSnapshot()
    expect(result.truncated).toBe(count > 5000)
    expect(result.events).toHaveLength(5000)
    expect(queries[4].range).toHaveBeenCalledWith(4000, 4999)
    expect(mocks.from).toHaveBeenCalledTimes(6)
  })
  it('fails an incomplete coverage read rather than claiming sources are current', async () => {
    page([]); page([], 2)
    await expect(getPublicFinanceSnapshot()).rejects.toThrow('source coverage was incomplete')
  })
  it('rejects a missing event or coverage payload even if the server reports zero rows', async () => {
    page(null, 0)
    await expect(getPublicFinanceSnapshot()).rejects.toThrow('count unavailable or changed')
    page([]); page(null, 0)
    await expect(getPublicFinanceSnapshot()).rejects.toThrow('source coverage was incomplete')
  })
  it('keeps query failures distinct from a complete empty projection', async () => {
    page([], 0, { code: 'timeout' })
    await expect(getPublicFinanceSnapshot()).rejects.toThrow('Finance projection unavailable')
    page([]); page([], 0, { code: 'timeout' })
    await expect(getPublicFinanceSnapshot()).rejects.toThrow('Finance source coverage unavailable')
    page([]); page([])
    expect(await getPublicFinanceSnapshot()).toEqual({ events: [], coverage: [], truncated: false })
  })
})
