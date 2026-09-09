import { beforeEach, describe, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'
const mocks = vi.hoisted(() => ({ from: vi.fn(), adminFrom: vi.fn(), admin: vi.fn(), auth: vi.fn() }))
vi.mock('@/lib/supabase', () => ({ supabase: { from: mocks.from } }))
vi.mock('@/lib/supabase-admin', () => ({ getSupabaseAdmin: mocks.admin }))
vi.mock('@/lib/operator-auth', () => ({ isOperatorAuthenticated: mocks.auth }))
import { GET } from './route'
const id = '11111111-1111-4111-8111-111111111111'
function flag(overrides = {}) {
  return { id, city_fips: '0660620', is_current: true, confidence: 0.9, false_positive: null,
    description: 'Source-backed flag detail', evidence: [], confidence_factors: {}, scanner_version: 'v4',
    flag_type: 'campaign_contribution', meeting_id: 'meeting', agenda_item_id: 'item', official_id: 'official',
    meetings: { id: 'meeting', meeting_date: '2026-04-08', city_fips: '0660620', source_cancelled_at: null },
    agenda_items: { id: 'item', meeting_id: 'meeting', title: 'Example item', item_number: 'H.1', category: null,
      agenda_source_retired_at: null, source_meeting: { id: 'meeting', city_fips: '0660620', source_cancelled_at: null } },
    officials: { id: 'official', name: 'Example Official' }, ...overrides }
}
function database(rows: ReturnType<typeof flag>[], options: { error?: object; count?: number | null; ignoreSourceFilters?: boolean } = {}) {
  let filtered = rows
  let single = false
  const field = (row: object, key: string): unknown => key.split('.').reduce<unknown>((value, part) =>
    value && typeof value === 'object' ? (value as Record<string, unknown>)[part] : undefined, row)
  const equal = (key: string, value: unknown) => {
    if (!(options.ignoreSourceFilters && key.includes('.'))) filtered = filtered.filter(row => field(row, key) === value)
    return query
  }
  const query = {
    select: vi.fn(), eq: vi.fn(equal), is: vi.fn(equal),
    gte: vi.fn((key: string, value: number) => { filtered = filtered.filter(row => Number((row as Record<string, unknown>)[key]) >= value); return query }),
    not: vi.fn((key: string, _op: string, value: unknown) => { filtered = filtered.filter(row => (row as Record<string, unknown>)[key] !== value); return query }),
    order: vi.fn(), limit: vi.fn(), maybeSingle: vi.fn(() => { single = true; return query }),
    then: (resolve: (result: object) => unknown) => Promise.resolve({ data: single ? filtered[0] ?? null : filtered,
      count: Object.hasOwn(options, 'count') ? options.count : filtered.length, error: options.error ?? null }).then(resolve),
  }
  for (const method of [query.select, query.order, query.limit]) method.mockReturnValue(query)
  mocks.from.mockReturnValue(query)
  mocks.adminFrom.mockReturnValue(query)
  return query
}
function request(query: string) { return new NextRequest(`https://example.test/api/flag-details?${query}`) }

describe('public UUID eligibility and private bulk source boundaries', () => {
  beforeEach(() => {
    vi.clearAllMocks(); mocks.from.mockReset(); mocks.adminFrom.mockReset(); mocks.auth.mockResolvedValue(true)
    mocks.admin.mockReturnValue({ from: mocks.adminFrom })
  })
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
    expect(mocks.auth).not.toHaveBeenCalled(); expect(mocks.admin).not.toHaveBeenCalled()
  })
  it('authenticates the bulk list first and explicitly preserves source eligibility without vote reads', async () => {
    const query = database([flag(), flag({ id: 'old', is_current: false }), flag({ id: 'low', confidence: 0.69 }), flag({ id: 'false', false_positive: true })])
    const response = await GET(request('all=1'))
    expect(response.status).toBe(200)
    const rows = await response.json()
    expect(rows).toEqual([expect.objectContaining({ id })])
    for (const key of ['vote_choice', 'motion_result', 'is_unanimous']) expect(rows[0]).not.toHaveProperty(key)
    expect(mocks.from).not.toHaveBeenCalled()
    expect(mocks.adminFrom.mock.calls).toEqual([['conflict_flags']])
    expect(mocks.auth.mock.invocationCallOrder[0]).toBeLessThan(mocks.admin.mock.invocationCallOrder[0])
    expect(query.is).toHaveBeenCalledWith('meetings.source_cancelled_at', null)
    expect(query.is).toHaveBeenCalledWith('agenda_items.agenda_source_retired_at', null)
    expect(query.is).toHaveBeenCalledWith('agenda_items.source_meeting.source_cancelled_at', null)
    expect(query.eq).toHaveBeenCalledWith('agenda_items.source_meeting.city_fips', '0660620')
    expect(response.headers.get('Cache-Control')).toBe('private, no-store')
  })
  it('rejects anonymous bulk requests before either client is used or admin constructed', async () => {
    mocks.auth.mockResolvedValue(false)
    const response = await GET(request('all=1'))
    expect(response.status).toBe(401)
    expect(response.headers.get('Cache-Control')).toBe('private, no-store')
    expect(mocks.from).not.toHaveBeenCalled(); expect(mocks.admin).not.toHaveBeenCalled(); expect(mocks.adminFrom).not.toHaveBeenCalled()
  })
  it('does not use admin when session validation fails', async () => {
    mocks.auth.mockRejectedValueOnce(new Error('private session detail'))
    const response = await GET(request('all=1'))
    expect(response.status).toBe(503)
    expect(await response.text()).not.toContain('private session')
    expect(response.headers.get('Cache-Control')).toBe('private, no-store')
    expect(mocks.admin).not.toHaveBeenCalled()
  })
  it.each(['flag-meeting', 'agenda-parent', 'retired', 'wrong-city'])('excludes withdrawn or foreign source records in the admin query: %s', async cause => {
    const original = flag()
    const invalid = cause === 'flag-meeting' ? flag({ meetings: { ...original.meetings, source_cancelled_at: '2026-01-01' } })
      : cause === 'retired' ? flag({ agenda_items: { ...original.agenda_items, agenda_source_retired_at: '2026-01-01' } })
        : flag({ agenda_items: { ...original.agenda_items, source_meeting: { ...original.agenda_items.source_meeting,
          ...(cause === 'wrong-city' ? { city_fips: 'elsewhere' } : { source_cancelled_at: '2026-01-01' }) } } })
    database([invalid])
    const response = await GET(request('all=1'))
    expect(response.status).toBe(200); expect(await response.json()).toEqual([])
  })
  it('rejects a source-identity mismatch or repeated record even if a backend returns them', async () => {
    const original = flag()
    database([flag({ agenda_items: { ...original.agenda_items, source_meeting: { ...original.agenda_items.source_meeting, id: 'wrong-parent' } } })])
    expect((await GET(request('all=1'))).status).toBe(503)
    database([flag(), flag()])
    expect((await GET(request('all=1'))).status).toBe(503)
    database([flag({ agenda_items: { ...original.agenda_items, meeting_id: 'different', source_meeting: { ...original.agenda_items.source_meeting, id: 'different' } } })])
    expect((await GET(request('all=1'))).status).toBe(503)
    database([flag({ meetings: { ...original.meetings, source_cancelled_at: '2026-01-01' } })], { ignoreSourceFilters: true })
    expect((await GET(request('all=1'))).status).toBe(503)
  })
  it.each([null, 2, 1001])('fails an incomplete/capped list instead of claiming all records: count %s', async count => {
    database([flag()], { count })
    const response = await GET(request('all=1'))
    expect(response.status).toBe(503)
    expect(response.headers.get('Cache-Control')).toBe('private, no-store')
  })
  it.each([`id=${id}`, 'all=1'])('redacts read failures without caching: %s', async query => {
    database([], { error: { message: 'private backend connection string' } })
    const response = await GET(request(query))
    expect(response.status).toBe(503)
    expect(await response.text()).not.toContain('private backend')
    expect(response.headers.get('Cache-Control')).toBe(query === 'all=1' ? 'private, no-store' : 'no-store')
  })
  it('rejects malformed UUID without a database call', async () => {
    expect((await GET(request('id=not-an-id'))).status).toBe(400)
    expect(mocks.from).not.toHaveBeenCalled()
  })
  it('rejects ambiguous single and bulk selection without authentication or database access', async () => {
    expect((await GET(request(`id=${id}&all=1`))).status).toBe(400)
    expect(mocks.auth).not.toHaveBeenCalled(); expect(mocks.from).not.toHaveBeenCalled(); expect(mocks.admin).not.toHaveBeenCalled()
  })
})
