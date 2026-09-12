import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { NextRequest } from 'next/server'

const mocks = vi.hoisted(() => ({
  getIronSession: vi.fn(),
}))

// Mock next/headers so getIronSession can be wired through the
// fake cookie store.
const cookieStore = new Map<string, string>()
vi.mock('next/headers', () => ({
  cookies: async () => cookieStore,
}))

// Mock iron-session so the session value is fully under test control.
let mockSession: { isOperator?: boolean } = {}
vi.mock('iron-session', () => ({
  getIronSession: mocks.getIronSession,
}))

import { isOperatorAuthenticated, withOperatorAuth } from './operator-auth'

function fakeNextRequest(): NextRequest {
  return {
    method: 'GET',
    url: 'https://example.com/api/operator/test',
    headers: { get: () => null },
  } as unknown as NextRequest
}

describe('withOperatorAuth', () => {
  beforeEach(() => {
    mockSession = {}
    mocks.getIronSession.mockReset()
    mocks.getIronSession.mockImplementation(async () => mockSession)
    cookieStore.clear()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('treats a deliberately secretless Vercel Preview as anonymous', async () => {
    vi.stubEnv('VERCEL_ENV', 'preview')
    vi.stubEnv('IRON_SESSION_PASSWORD', '')
    mockSession = { isOperator: true }

    await expect(isOperatorAuthenticated()).resolves.toBe(false)
    expect(mocks.getIronSession).not.toHaveBeenCalled()
  })

  it('fails closed when the session secret is missing outside a Vercel Preview', async () => {
    vi.stubEnv('VERCEL_ENV', 'production')
    vi.stubEnv('NODE_ENV', 'production')
    vi.stubEnv('IRON_SESSION_PASSWORD', '')
    mockSession = { isOperator: true }

    await expect(isOperatorAuthenticated()).rejects.toThrow(
      'IRON_SESSION_PASSWORD is required in production',
    )
    expect(mocks.getIronSession).not.toHaveBeenCalled()
  })

  it('returns 401 when session has no isOperator flag', async () => {
    mockSession = {}
    const inner = vi.fn(() => new Response('OK', { status: 200 }))
    const wrapped = withOperatorAuth(inner)

    const res = await wrapped(fakeNextRequest())

    expect(res.status).toBe(401)
    expect(inner).not.toHaveBeenCalled()
    const body = await res.json()
    expect(body).toEqual({ error: 'Unauthorized' })
  })

  it('returns 401 when isOperator is explicitly false', async () => {
    mockSession = { isOperator: false }
    const inner = vi.fn(() => new Response('OK', { status: 200 }))
    const wrapped = withOperatorAuth(inner)

    const res = await wrapped(fakeNextRequest())

    expect(res.status).toBe(401)
    expect(inner).not.toHaveBeenCalled()
  })

  it('invokes the wrapped handler when isOperator is true', async () => {
    mockSession = { isOperator: true }
    const inner = vi.fn(() => new Response('OK', { status: 200 }))
    const wrapped = withOperatorAuth(inner)

    const res = await wrapped(fakeNextRequest())

    expect(res.status).toBe(200)
    expect(inner).toHaveBeenCalledTimes(1)
  })

  it('passes additional args through to the wrapped handler', async () => {
    mockSession = { isOperator: true }
    const inner = vi.fn(
      (_req: NextRequest, args: { params: { id: string } }) =>
        new Response(JSON.stringify({ id: args.params.id }), { status: 200 }),
    )
    const wrapped = withOperatorAuth(inner)

    const res = await wrapped(fakeNextRequest(), { params: { id: 'abc' } })
    expect(res.status).toBe(200)
    expect(await res.json()).toEqual({ id: 'abc' })
  })
})
