import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { NextRequest } from 'next/server'

const mock = vi.hoisted(() => ({
  session: { isOperator: false },
  getAdmin: vi.fn(),
  from: vi.fn(),
  rpc: vi.fn(),
}))

vi.mock('next/headers', () => ({ cookies: async () => ({}) }))
vi.mock('next/cache', () => ({ revalidateTag: vi.fn() }))
vi.mock('iron-session', () => ({ getIronSession: async () => mock.session }))
vi.mock('@/lib/operator-session', () => ({ getOperatorSessionOptions: () => ({}) }))
vi.mock('@/lib/supabase-admin', () => ({ getSupabaseAdmin: mock.getAdmin }))
// A regression to the anonymous client must fail even if its mock returns data.
vi.mock('@/lib/supabase', () => ({
  supabase: { from: () => { throw new Error('Private decision read used anon') } },
}))

import { GET, POST } from './route'

const request = { method: 'GET' } as NextRequest

function query(data: unknown[], error: { message: string } | null = null) {
  const result = { data, error }
  const chain = {
    select: vi.fn(), eq: vi.fn(), neq: vi.fn(), in: vi.fn(), order: vi.fn(),
    limit: vi.fn().mockResolvedValue(result),
    then: (resolve: (value: typeof result) => unknown) => Promise.resolve(result).then(resolve),
  }
  for (const method of [chain.select, chain.eq, chain.neq, chain.in, chain.order]) {
    method.mockReturnValue(chain)
  }
  return chain
}

describe('operator decision access', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mock.session.isOperator = false
    mock.getAdmin.mockReturnValue({ from: mock.from, rpc: mock.rpc })
  })

  it('rejects anonymous requests before creating a service-role client', async () => {
    const response = await GET(request)
    expect(response.status).toBe(401)
    expect(mock.getAdmin).not.toHaveBeenCalled()
    expect(mock.from).not.toHaveBeenCalled()
  })

  it('reads and sorts private decisions for an authenticated operator', async () => {
    mock.session.isOperator = true
    const pending = [
      { id: 'new-low', status: 'pending', severity: 'low', created_at: '2026-09-06' },
      { id: 'older-high', status: 'pending', severity: 'high', created_at: '2026-09-04' },
      { id: 'newer-high', status: 'pending', severity: 'high', created_at: '2026-09-05' },
    ]
    mock.from.mockReturnValueOnce(query(pending)).mockReturnValueOnce(query([])).mockReturnValueOnce(query([]))
    const response = await GET(request)
    expect(response.status).toBe(200)
    expect(mock.getAdmin).toHaveBeenCalledTimes(1)
    expect(mock.from.mock.calls).toEqual([['pending_decisions'], ['pending_decisions'], ['operator_decision_events']])
    const body = await response.json()
    expect(body.pending.map((row: { id: string }) => row.id))
      .toEqual(['older-high', 'newer-high', 'new-low'])
    expect(body.summary.counts.high).toBe(2)
  })

  it('reports unavailable private data instead of a false empty queue', async () => {
    mock.session.isOperator = true
    mock.from.mockReturnValueOnce(query([], { message: 'unavailable' }))
      .mockReturnValueOnce(query([]))
    const response = await GET(request)
    expect(response.status).toBe(500)
    expect(await response.json()).toEqual({ error: 'Failed to fetch decision queue' })
  })
})

const payload = {
  decision_id: '11111111-1111-4111-8111-111111111111', action: 'approve', expected_version: 3,
  idempotency_key: '22222222-2222-4222-8222-222222222222', note: 'Sources checked.',
}
function post(body: unknown = payload, origin: string | null = 'https://richmondcommons.org', site = 'same-origin') {
  const headers: Record<string, string> = { 'Content-Type': 'application/json', 'Sec-Fetch-Site': site }
  if (origin !== null) headers.Origin = origin
  return new Request('https://richmondcommons.org/api/operator/decisions', {
    method: 'POST', headers, body: JSON.stringify(body),
  }) as NextRequest
}

describe('review action authentication and concurrency contract', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mock.session.isOperator = true
    mock.getAdmin.mockReturnValue({ from: mock.from, rpc: mock.rpc })
  })

  it('denies unauthenticated mutation before database access', async () => {
    mock.session.isOperator = false
    expect((await POST(post())).status).toBe(401)
    expect(mock.getAdmin).not.toHaveBeenCalled()
  })

  it.each([
    ['https://attacker.invalid', 'cross-site'], [null, 'same-origin'],
    ['https://richmondcommons.org', 'cross-site'],
  ])('denies cross-origin or missing-origin requests (%s)', async (origin, site) => {
    expect((await POST(post(payload, origin, site!))).status).toBe(403)
    expect(mock.getAdmin).not.toHaveBeenCalled()
  })

  it.each([
    { ...payload, action: 'run_sql' }, { ...payload, sql: 'DROP TABLE meetings' },
    { ...payload, expected_version: 0 }, { ...payload, expected_version: 1.5 },
    { ...payload, idempotency_key: 'missing' }, { ...payload, note: 'x'.repeat(4001) },
  ])('rejects unsupported or unguarded request %#', async body => {
    expect((await POST(post(body))).status).toBe(400)
    expect(mock.rpc).not.toHaveBeenCalled()
  })

  it('sends only the whitelisted action and reviewed version to the atomic RPC', async () => {
    mock.rpc.mockResolvedValue({ data: { ok: true, effect: 'decision_recorded' }, error: null })
    expect((await POST(post())).status).toBe(200)
    expect(mock.rpc).toHaveBeenCalledWith('review_decision', {
      p_decision_id: payload.decision_id, p_action: 'approve', p_expected_version: 3,
      p_idempotency_key: payload.idempotency_key, p_note: 'Sources checked.', p_actor: 'operator',
    })
  })

  it('returns a stale-review conflict without pretending the action succeeded', async () => {
    mock.rpc.mockResolvedValue({ data: { ok: false, code: 'stale_decision' }, error: null })
    const response = await POST(post())
    expect(response.status).toBe(409)
    expect(await response.json()).toEqual({ ok: false, code: 'stale_decision' })
  })

  it('does not expose database diagnostics to the browser', async () => {
    mock.rpc.mockResolvedValue({ data: null, error: { code: 'XX000', message: 'private diagnostic' } })
    const response = await POST(post())
    expect(response.status).toBe(500)
    expect(JSON.stringify(await response.json())).not.toContain('private diagnostic')
  })
})
