import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest'
import type { NextRequest } from 'next/server'

const mocked = vi.hoisted(() => ({
  getSupabaseAdmin: vi.fn(),
  rpc: vi.fn(),
  from: vi.fn(),
  deleteRows: vi.fn(),
  lt: vi.fn(),
  like: vi.fn(),
}))

vi.mock('./supabase-admin', () => ({
  getSupabaseAdmin: mocked.getSupabaseAdmin,
}))

import { clientKey, enforceRateLimit, limits } from './rate-limit'

function fakeRequest(headers: Record<string, string>): NextRequest {
  const headerMap = new Map(Object.entries(headers).map(([k, v]) => [k.toLowerCase(), v]))
  return {
    headers: {
      get: (name: string) => headerMap.get(name.toLowerCase()) ?? null,
    },
  } as unknown as NextRequest
}

describe('clientKey', () => {
  const originalSessionPassword = process.env.IRON_SESSION_PASSWORD

  beforeEach(() => {
    process.env.IRON_SESSION_PASSWORD = 'test-only-rate-limit-hmac-secret-32-chars'
  })

  afterEach(() => {
    if (originalSessionPassword === undefined) {
      delete process.env.IRON_SESSION_PASSWORD
    } else {
      process.env.IRON_SESSION_PASSWORD = originalSessionPassword
    }
  })

  it('pseudonymizes the first IP from x-forwarded-for', () => {
    const req = fakeRequest({ 'x-forwarded-for': '203.0.113.5, 10.0.0.1' })
    expect(clientKey(req)).toMatch(/^h1d:\d{8}:[0-9a-f]{64}$/)
    expect(clientKey(req)).not.toContain('203.0.113.5')
  })

  it('pseudonymizes x-real-ip when forwarded-for is missing', () => {
    const req = fakeRequest({ 'x-real-ip': '198.51.100.7' })
    expect(clientKey(req)).toMatch(/^h1d:\d{8}:[0-9a-f]{64}$/)
    expect(clientKey(req)).not.toContain('198.51.100.7')
  })

  it('falls back to the provided default when both headers are missing', () => {
    const req = fakeRequest({})
    expect(clientKey(req, 'unknown')).toBe('unknown')
  })

  it('default fallback is "anon"', () => {
    const req = fakeRequest({})
    expect(clientKey(req)).toBe('anon')
  })

  it('trims whitespace around the first forwarded entry', () => {
    const padded = fakeRequest({ 'x-forwarded-for': '   192.0.2.1   , 10.0.0.1' })
    const plain = fakeRequest({ 'x-forwarded-for': '192.0.2.1' })
    expect(clientKey(padded)).toBe(clientKey(plain))
  })

  it('rotates the pseudonym at the UTC day boundary', () => {
    vi.useFakeTimers()
    const req = fakeRequest({ 'x-forwarded-for': '192.0.2.1' })
    vi.setSystemTime(new Date('2026-08-15T23:59:59Z'))
    const firstDay = clientKey(req)
    vi.setSystemTime(new Date('2026-08-16T00:00:00Z'))
    const secondDay = clientKey(req)
    vi.useRealTimers()

    expect(firstDay).not.toBe(secondDay)
    expect(firstDay).toMatch(/^h1d:20260815:/)
    expect(secondDay).toMatch(/^h1d:20260816:/)
  })

  it('does not persist an address when the server-only HMAC secret is unavailable', () => {
    delete process.env.IRON_SESSION_PASSWORD
    const req = fakeRequest({ 'x-forwarded-for': '192.0.2.1' })
    expect(clientKey(req, 'unknown')).toBe('unknown')
  })
})

describe('limits config', () => {
  it('has all six expected buckets', () => {
    expect(Object.keys(limits).sort()).toEqual(
      ['comments', 'feedback', 'login', 'revalidate', 'search', 'subscribe'],
    )
  })

  it('login bucket is the tightest (5 attempts / 15 min)', () => {
    expect(limits.login.maxCount).toBe(5)
    expect(limits.login.windowSecs).toBe(15 * 60)
  })

  it('subscribe and comments are hourly', () => {
    expect(limits.subscribe.windowSecs).toBe(3600)
    expect(limits.comments.windowSecs).toBe(3600)
  })

  it('revalidate allows 60/min for legitimate cache busts', () => {
    expect(limits.revalidate.windowSecs).toBe(60)
    expect(limits.revalidate.maxCount).toBe(60)
  })

  it('search preserves the former 15/min per-IP boundary', () => {
    expect(limits.search.windowSecs).toBe(60)
    expect(limits.search.maxCount).toBe(15)
  })
})

describe('enforceRateLimit backend authority', () => {
  const originalSessionPassword = process.env.IRON_SESSION_PASSWORD

  beforeEach(() => {
    process.env.IRON_SESSION_PASSWORD = 'test-only-rate-limit-hmac-secret-32-chars'
    mocked.getSupabaseAdmin.mockReset()
    mocked.rpc.mockReset()
    mocked.from.mockReset()
    mocked.deleteRows.mockReset()
    mocked.lt.mockReset()
    mocked.like.mockReset()
    mocked.getSupabaseAdmin.mockReturnValue({ rpc: mocked.rpc, from: mocked.from })
    mocked.from.mockReturnValue({ delete: mocked.deleteRows })
    mocked.deleteRows.mockReturnValue({ lt: mocked.lt })
    mocked.lt.mockReturnValue({ like: mocked.like })
    mocked.like.mockResolvedValue({ error: null })
  })

  afterEach(() => {
    if (originalSessionPassword === undefined) {
      delete process.env.IRON_SESSION_PASSWORD
    } else {
      process.env.IRON_SESSION_PASSWORD = originalSessionPassword
    }
    vi.restoreAllMocks()
  })

  it('marks an RPC failure unavailable so it cannot authorize paid work', async () => {
    mocked.rpc.mockResolvedValue({
      data: null,
      error: { message: 'database unavailable' },
    })
    vi.spyOn(console, 'error').mockImplementation(() => undefined)

    const result = await enforceRateLimit('search', '203.0.113.5')

    expect(result).toEqual({ allowed: true, backendAvailable: false })
  })

  it('marks a successful counter increment as authoritative', async () => {
    mocked.rpc.mockResolvedValue({
      data: [{ allowed: true, retry_after_secs: 60 }],
      error: null,
    })

    const result = await enforceRateLimit('search', '203.0.113.5')

    expect(result).toEqual({ allowed: true, backendAvailable: true })
    expect(mocked.rpc).toHaveBeenCalledWith('check_and_increment_rate_limit', {
      p_bucket_key: expect.stringMatching(/^search:h1d:\d{8}:[0-9a-f]{64}$/),
      p_max_count: 15,
      p_window_secs: 60,
    })
    const args = mocked.rpc.mock.calls[0][1] as { p_bucket_key: string }
    expect(args.p_bucket_key).not.toContain('203.0.113.5')
  })

  it('prunes only expired versioned pseudonyms and never legacy raw-IP buckets', async () => {
    vi.resetModules()
    const { enforceRateLimit: enforceWithFreshCleanupState } = await import('./rate-limit')
    mocked.rpc.mockResolvedValue({
      data: [{ allowed: true, retry_after_secs: 60 }],
      error: null,
    })

    await enforceWithFreshCleanupState('search', `h1d:20260815:${'a'.repeat(64)}`)

    expect(mocked.from).toHaveBeenCalledWith('rate_limit_buckets')
    expect(mocked.deleteRows).toHaveBeenCalledTimes(1)
    expect(mocked.lt).toHaveBeenCalledWith('window_start', expect.any(String))
    expect(mocked.like).toHaveBeenCalledWith('bucket_key', '%:h1d:%')
  })

  it('returns 429 only for an authoritative exceeded counter', async () => {
    mocked.rpc.mockResolvedValue({
      data: [{ allowed: false, retry_after_secs: 42 }],
      error: null,
    })

    const result = await enforceRateLimit('search', '203.0.113.5')

    expect(result.allowed).toBe(false)
    expect(result.backendAvailable).toBe(true)
    expect(result.response?.status).toBe(429)
    expect(result.response?.headers.get('Retry-After')).toBe('42')
  })
})
