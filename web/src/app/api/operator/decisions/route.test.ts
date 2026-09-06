import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { NextRequest } from 'next/server'

const mock = vi.hoisted(() => ({
  session: { isOperator: false },
  getAdmin: vi.fn(),
  from: vi.fn(),
}))

vi.mock('next/headers', () => ({ cookies: async () => ({}) }))
vi.mock('iron-session', () => ({ getIronSession: async () => mock.session }))
vi.mock('@/lib/operator-session', () => ({ getOperatorSessionOptions: () => ({}) }))
vi.mock('@/lib/supabase-admin', () => ({ getSupabaseAdmin: mock.getAdmin }))
// A regression to the anonymous client must fail even if its mock returns data.
vi.mock('@/lib/supabase', () => ({
  supabase: { from: () => { throw new Error('Private decision read used anon') } },
}))

import { GET } from './route'

const request = { method: 'GET' } as NextRequest

function query(data: unknown[], error: { message: string } | null = null) {
  const result = { data, error }
  const chain = {
    select: vi.fn(), eq: vi.fn(), neq: vi.fn(), order: vi.fn(),
    limit: vi.fn().mockResolvedValue(result),
    then: (resolve: (value: typeof result) => unknown) => Promise.resolve(result).then(resolve),
  }
  for (const method of [chain.select, chain.eq, chain.neq, chain.order]) {
    method.mockReturnValue(chain)
  }
  return chain
}

describe('operator decision access', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mock.session.isOperator = false
    mock.getAdmin.mockReturnValue({ from: mock.from })
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
      { id: 'new-low', severity: 'low', created_at: '2026-09-06' },
      { id: 'older-high', severity: 'high', created_at: '2026-09-04' },
      { id: 'newer-high', severity: 'high', created_at: '2026-09-05' },
    ]
    mock.from.mockReturnValueOnce(query(pending)).mockReturnValueOnce(query([]))
    const response = await GET(request)
    expect(response.status).toBe(200)
    expect(mock.getAdmin).toHaveBeenCalledTimes(1)
    expect(mock.from.mock.calls).toEqual([['pending_decisions'], ['pending_decisions']])
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
