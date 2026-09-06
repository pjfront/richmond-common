import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ from: vi.fn() }))
vi.mock('next/cache', () => ({ unstable_cache: (fn: unknown) => fn }))
vi.mock('@/lib/supabase', () => ({ supabase: { from: mocks.from } }))

import { getPublicFinanceSnapshot, PUBLIC_FINANCE_SCOPE } from './finance-public'

function builder(result: object) {
  const query = {
    select: vi.fn(), eq: vi.fn(), gte: vi.fn(), lte: vi.fn(), order: vi.fn(), range: vi.fn(), limit: vi.fn(),
    then: (resolve: (value: object) => unknown) => Promise.resolve(result).then(resolve),
  }
  for (const method of [query.select, query.eq, query.gte, query.lte, query.order, query.range, query.limit]) method.mockReturnValue(query)
  return query
}
const row = { event_key: 'correction', scope_key: PUBLIC_FINANCE_SCOPE, amount: '-25.10', amount_kind: 'negative_adjustment', source_url: 'https://netfile.com/filing/1', source_urls: ['https://netfile.com/filing/1'], extracted_at: '2026-09-06T12:00:00Z' }

describe('public finance projection', () => {
  beforeEach(() => { mocks.from.mockReset() })

  it('preserves signed amount semantics and queries events and acquisition windows in the same Richmond scope', async () => {
    const events = builder({ data: [row], error: null })
    const coverage = builder({ data: [{ scope_key: PUBLIC_FINANCE_SCOPE, activity_from: '2026-01-01', activity_through: '2026-09-06' }], error: null })
    mocks.from.mockReturnValueOnce(events).mockReturnValueOnce(coverage)
    const result = await getPublicFinanceSnapshot()
    expect(result.events[0]).toEqual({ ...row, amount: -25.10 })
    expect(events.select.mock.calls[0][0].split(',')).toEqual(expect.arrayContaining(['amount_kind', 'scope_key', 'source_urls']))
    expect(coverage.select.mock.calls[0][0].split(',')).toEqual(expect.arrayContaining(['activity_from', 'activity_through']))
    expect(events.eq).toHaveBeenCalledWith('scope_key', PUBLIC_FINANCE_SCOPE)
    expect(coverage.eq).toHaveBeenCalledWith('scope_key', PUBLIC_FINANCE_SCOPE)
    expect(result.coverage[0].activity_through).toBe('2026-09-06')
    expect(result.truncated).toBe(false)
  })

  it('fails explicitly when an amount lacks the source type needed to interpret it', async () => {
    mocks.from.mockReturnValueOnce(builder({ data: [{ ...row, amount_kind: null }], error: null }))
    await expect(getPublicFinanceSnapshot()).rejects.toThrow('incomplete provenance or amount')
    expect(mocks.from).toHaveBeenCalledTimes(1)
  })

  it('marks the bounded snapshot incomplete when all five thousand-record pages are full', async () => {
    const fullPage = builder({ data: Array.from({ length: 1000 }, (_, index) => ({ ...row, event_key: `event-${index}` })), error: null })
    for (let page = 0; page < 5; page++) mocks.from.mockReturnValueOnce(fullPage)
    mocks.from.mockReturnValueOnce(builder({ data: [], error: null }))
    const result = await getPublicFinanceSnapshot()
    expect(result.truncated).toBe(true)
    expect(result.events).toHaveLength(5000)
    expect(fullPage.range).toHaveBeenLastCalledWith(4000, 4999)
    expect(mocks.from).toHaveBeenCalledTimes(6)
  })
})
