import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { NextRequestRequest } from '../types'
const mocks = vi.hoisted(() => ({ from: vi.fn() }))
vi.mock('react', () => ({ cache: (fn: unknown) => fn }))
vi.mock('./_shared', () => ({ supabase: { from: mocks.from }, RICHMOND_FIPS: '0660620', COLS_PUBLIC_RECORD_LIST: 'id,status,days_to_close,department' }))
import { getPublicRecordsSnapshot, summarizePublicRecords } from './public_records'

function row(id: string, overrides = {}): NextRequestRequest {
  return { id, status: 'Open', days_to_close: null, department: 'Clerk', ...overrides } as NextRequestRequest
}
function page(data: object[] | null, count: number | null, error: object | null = null) {
  const query = { select: vi.fn(), eq: vi.fn(), is: vi.fn(), order: vi.fn(), range: vi.fn(),
    then: (resolve: (value: object) => unknown) => Promise.resolve({ data, count, error }).then(resolve) }
  for (const method of [query.select, query.eq, query.is, query.order, query.range]) method.mockReturnValue(query)
  mocks.from.mockReturnValueOnce(query)
  return query
}
describe('complete observed public-record snapshot', () => {
  beforeEach(() => mocks.from.mockReset())
  it('uses one paginated cohort for records, departments and summary', async () => {
    const first = page(Array.from({ length: 500 }, (_, i) => row(String(i))), 501)
    const second = page([row('last', { status: 'Closed', days_to_close: 35, department: 'Planning' })], 501)
    const result = await getPublicRecordsSnapshot()
    expect(result.requests).toHaveLength(501)
    expect(result.stats).toEqual({ totalRequests: 501, closedRequests: 1, notClosedRequests: 500, closureTimingCount: 1, avgClosureDays: 35 })
    expect(result.departments).toContainEqual({ department: 'Planning', requestCount: 1, closedCount: 1, closureTimingCount: 1, avgClosureDays: 35 })
    expect(first.range).toHaveBeenCalledWith(0, 499)
    expect(second.range).toHaveBeenCalledWith(500, 999)
    expect(first.order.mock.calls).toEqual([['submitted_date', { ascending: false }], ['id', { ascending: true }]])
    expect(first.is).toHaveBeenCalledWith('source_removed_at', null)
    expect(first.select).toHaveBeenCalledWith(expect.any(String), { count: 'exact' })
  })
  it('advances by actual returned rows under a smaller server cap', async () => {
    page([row('1')], 2)
    const second = page([row('2')], 2)
    expect((await getPublicRecordsSnapshot()).stats.totalRequests).toBe(2)
    expect(second.range).toHaveBeenCalledWith(1, 500)
  })
  it('returns a real empty cohort only after a successful exact zero count', async () => {
    page([], 0)
    expect((await getPublicRecordsSnapshot()).stats).toEqual({ totalRequests: 0, closedRequests: 0, notClosedRequests: 0, closureTimingCount: 0, avgClosureDays: null })
  })
  it.each(['first-error', 'late-error', 'missing-count', 'changed-count', 'duplicate', 'empty-later', 'too-many', 'null-data', 'extra-row'])('rejects incomplete snapshots: %s', async cause => {
    if (cause === 'first-error') page(null, null, { code: 'XX000', message: 'private' })
    else if (cause === 'missing-count') page([row('1')], null)
    else if (cause === 'too-many') page([row('1')], 10001)
    else if (cause === 'null-data') page(null, 0)
    else if (cause === 'extra-row') page([row('1')], 0)
    else {
      page([row('1')], 2)
      if (cause === 'late-error') page(null, null, { code: '57014' })
      if (cause === 'changed-count') page([row('2')], 3)
      if (cause === 'duplicate') page([row('1')], 2)
      if (cause === 'empty-later') page([], 2)
    }
    await expect(getPublicRecordsSnapshot()).rejects.toThrow('temporarily unavailable')
  })
  it('bounds requests even if the server returns one row per page', async () => {
    for (let i = 0; i < 20; i++) page([row(String(i))], 21)
    await expect(getPublicRecordsSnapshot()).rejects.toThrow('temporarily unavailable')
    expect(mocks.from).toHaveBeenCalledTimes(20)
  })
  it('does not reinterpret closed duration as first response or count open timing as closed', () => {
    const result = summarizePublicRecords([
      row('closed', { status: ' CLOSED ', days_to_close: 35 }),
      row('completed', { status: 'Completed', days_to_close: 0 }),
      row('open', { days_to_close: 1 }),
      row('unknown', { status: null, days_to_close: 2 }),
      ...[null, -1, Infinity, Number.NaN, 1.5].map((days, i) => row(`invalid${i}`, { status: 'Closed', days_to_close: days })),
    ])
    expect(result).toEqual({ totalRequests: 9, closedRequests: 7, notClosedRequests: 2, closureTimingCount: 2, avgClosureDays: 18 })
    expect(result).not.toHaveProperty('onTimeRate')
    expect(result).not.toHaveProperty('currentlyOverdue')
  })
})
