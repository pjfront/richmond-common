import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'
const mocks = vi.hoisted(() => ({ from: vi.fn(), rpc: vi.fn(), session: { isOperator: false } }))
vi.mock('@/lib/supabase', () => ({ supabase: { from: mocks.from, rpc: mocks.rpc } }))
vi.mock('next/headers', () => ({ cookies: async () => ({}) }))
vi.mock('iron-session', () => ({ getIronSession: async () => mocks.session }))
vi.mock('@/lib/operator-session', () => ({ getOperatorSessionOptions: () => ({ password: 'x'.repeat(32), cookieName: 'test' }) }))
import { GET } from './route'
function query(data: object[] | null, count: number | null = data?.length ?? null, error: object | null = null) {
  const q = { select: vi.fn(), eq: vi.fn(), is: vi.fn(), in: vi.fn(), gte: vi.fn(), filter: vi.fn(), order: vi.fn(), limit: vi.fn(),
    then: (resolve: (v: object) => unknown) => Promise.resolve({ data, count, error }).then(resolve) }
  for (const method of [q.select, q.eq, q.is, q.in, q.gte, q.filter, q.order, q.limit]) method.mockReturnValue(q)
  mocks.from.mockReturnValueOnce(q)
}
const req = () => new NextRequest('https://example.test/api/data-quality')
const coverage = [{ total: 100, has_minutes: 80, has_agenda: 90, has_video: 70 }]
const meeting = { id: 'one', meeting_date: '2026-09-01', meeting_type: 'regular', minutes_url: 'https://source.test/minutes', agenda_url: null, video_url: null }
describe('operator-only diagnostic integrity', () => {
  beforeEach(() => { mocks.from.mockReset(); mocks.rpc.mockReset(); mocks.session.isOperator = true; vi.spyOn(console, 'error').mockImplementation(() => {}); mocks.rpc.mockResolvedValue({ data: coverage, error: null }) })
  afterEach(() => vi.restoreAllMocks())
  it('authenticates before any database read', async () => {
    mocks.session.isOperator = false
    const response = await GET(req())
    expect(response.status).toBe(401)
    expect(mocks.from).not.toHaveBeenCalled()
    expect(mocks.rpc).not.toHaveBeenCalled()
  })
  it.each(['freshness', 'meetings', 'rpc'])('does not cache failed required reads as healthy: %s', async cause => {
    query(cause === 'freshness' ? null : [], null, cause === 'freshness' ? { code: 'XX000' } : null)
    query(cause === 'meetings' ? null : [], null, cause === 'meetings' ? { code: 'XX000' } : null)
    if (cause === 'rpc') mocks.rpc.mockResolvedValue({ data: null, error: { message: 'private diagnostic' } })
    const response = await GET(req())
    expect(response.status).toBe(503)
    expect(response.headers.get('Cache-Control')).toBe('private, no-store')
    expect(await response.text()).not.toContain('private diagnostic')
  })
  it('never substitutes the recent sample for missing overall coverage', async () => {
    query([]); query([])
    mocks.rpc.mockResolvedValue({ data: [], error: null })
    const response = await GET(req())
    expect(response.status).toBe(503)
  })
  it.each(['object', 'array'])('counts supported join shape and keeps the actual full-coverage denominator: %s', async shape => {
    query([]); query([meeting])
    query([{ meeting_id: 'one' }])
    query([{ motion_id: 'motion', motions: shape === 'object' ? { agenda_items: { meeting_id: 'one' } } : [{ agenda_items: [{ meeting_id: 'one' }] }] }])
    query([{ meeting_id: 'one' }]); query([])
    const response = await GET(req())
    expect(response.status).toBe(200)
    expect(response.headers.get('Cache-Control')).toBe('private, no-store')
    const body = await response.json()
    expect(body.completeness.total_meetings).toBe(100)
    expect(body.completeness.recent_meetings[0].vote_count).toBe(1)
  })
  it.each(['items', 'votes', 'attendance', 'baseline'])('rejects truncated or failed child diagnostics: %s', async cause => {
    query([]); query([meeting])
    query([], cause === 'items' ? 3 : 0)
    query([], cause === 'votes' ? 3 : 0)
    query([], cause === 'attendance' ? 3 : 0)
    if (cause === 'baseline') query(null, null, { code: '57014' })
    const response = await GET(req())
    expect(response.status).toBe(503)
  })
})
