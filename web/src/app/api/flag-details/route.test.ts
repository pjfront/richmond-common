import { beforeEach, describe, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'
const mocks = vi.hoisted(() => ({ from: vi.fn() }))
vi.mock('@/lib/supabase', () => ({ supabase: { from: mocks.from } }))
import { GET } from './route'
const id = '11111111-1111-4111-8111-111111111111'
function flag(overrides = {}) {
  return { id, city_fips: '0660620', is_current: true, confidence: 0.9, false_positive: null,
    description: 'Source-backed flag detail', evidence: [], confidence_factors: {}, scanner_version: 'v4',
    flag_type: 'campaign_contribution', meeting_id: 'meeting', agenda_item_id: 'item', official_id: 'official',
    meetings: { meeting_date: '2026-04-08' }, agenda_items: { title: 'Example item', item_number: 'H.1', category: null },
    officials: { name: 'Example Official' }, ...overrides }
}
function database(rows: ReturnType<typeof flag>[], options: { error?: object; count?: number | null } = {}) {
  let filtered = rows
  let single = false
  const query = {
    select: vi.fn(), eq: vi.fn((key: string, value: unknown) => { filtered = filtered.filter(row => (row as Record<string, unknown>)[key] === value); return query }),
    gte: vi.fn((key: string, value: number) => { filtered = filtered.filter(row => Number((row as Record<string, unknown>)[key]) >= value); return query }),
    not: vi.fn((key: string, _op: string, value: unknown) => { filtered = filtered.filter(row => (row as Record<string, unknown>)[key] !== value); return query }),
    order: vi.fn(), limit: vi.fn(), maybeSingle: vi.fn(() => { single = true; return query }),
    then: (resolve: (result: object) => unknown) => Promise.resolve({ data: single ? filtered[0] ?? null : filtered,
      count: Object.hasOwn(options, 'count') ? options.count : filtered.length, error: options.error ?? null }).then(resolve),
  }
  for (const method of [query.select, query.order, query.limit]) method.mockReturnValue(query)
  mocks.from.mockReturnValue(query)
  return query
}
function request(query: string) { return new NextRequest(`https://example.test/api/flag-details?${query}`) }

describe('identical public flag boundaries', () => {
  beforeEach(() => mocks.from.mockReset())
  it.each([{ is_current: false }, { confidence: 0.69 }, { false_positive: true }, { city_fips: '9999999' }])('withholds excluded UUID details: %j', async overrides => {
    database([flag(overrides)])
    const response = await GET(request(`id=${id}`))
    expect(response.status).toBe(404)
    expect(await response.text()).not.toContain('Source-backed flag detail')
  })
  it('allows the existing confidence boundary and unknown false-positive status without inventing approval', async () => {
    const query = database([flag({ confidence: 0.7 })])
    const response = await GET(request(`id=${id}`))
    expect(response.status).toBe(200)
    expect(query.eq).toHaveBeenCalledWith('is_current', true)
    expect(query.gte).toHaveBeenCalledWith('confidence', 0.7)
    expect(query.not).toHaveBeenCalledWith('false_positive', 'is', true)
  })
  it('filters list identically and never queries partial votes', async () => {
    database([flag(), flag({ id: 'old', is_current: false }), flag({ id: 'low', confidence: 0.69 }), flag({ id: 'false', false_positive: true })])
    const response = await GET(request('all=1'))
    expect(response.status).toBe(200)
    expect(await response.json()).toEqual([expect.objectContaining({ id, vote_choice: null, motion_result: null, is_unanimous: null })])
    expect(mocks.from.mock.calls).toEqual([['conflict_flags']])
  })
  it.each([null, 2, 1001])('fails an incomplete/capped list instead of claiming all records: count %s', async count => {
    database([flag()], { count })
    const response = await GET(request('all=1'))
    expect(response.status).toBe(503)
    expect(response.headers.get('Cache-Control')).toBe('no-store')
  })
  it.each([`id=${id}`, 'all=1'])('redacts read failures without caching: %s', async query => {
    database([], { error: { message: 'private backend connection string' } })
    const response = await GET(request(query))
    expect(response.status).toBe(503)
    expect(await response.text()).not.toContain('private backend')
    expect(response.headers.get('Cache-Control')).toBe('no-store')
  })
  it('rejects malformed UUID without a database call', async () => {
    expect((await GET(request('id=not-an-id'))).status).toBe(400)
    expect(mocks.from).not.toHaveBeenCalled()
  })
})
