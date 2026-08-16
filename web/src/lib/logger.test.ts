import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { logEvent, requestContext, emailHash } from './logger'
import type { NextRequest } from 'next/server'

describe('logEvent', () => {
  let consoleLogSpy: ReturnType<typeof vi.spyOn>
  let consoleWarnSpy: ReturnType<typeof vi.spyOn>
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    consoleLogSpy = vi.spyOn(console, 'log').mockImplementation(() => undefined)
    consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('emits one JSON line with ts, severity, event', () => {
    logEvent('test.event', { foo: 'bar' })
    expect(consoleLogSpy).toHaveBeenCalledTimes(1)
    const line = consoleLogSpy.mock.calls[0][0] as string
    const parsed = JSON.parse(line)
    expect(parsed.event).toBe('test.event')
    expect(parsed.severity).toBe('info')
    expect(parsed.foo).toBe('bar')
    expect(typeof parsed.ts).toBe('string')
    expect(parsed.ts).toMatch(/^\d{4}-\d{2}-\d{2}T/)
  })

  it('routes warn severity through console.warn', () => {
    logEvent('test.warn', { severity: 'warn' })
    expect(consoleWarnSpy).toHaveBeenCalledTimes(1)
    expect(consoleLogSpy).not.toHaveBeenCalled()
  })

  it('routes error severity through console.error', () => {
    logEvent('test.err', { severity: 'error', message: 'boom' })
    expect(consoleErrorSpy).toHaveBeenCalledTimes(1)
    expect(consoleLogSpy).not.toHaveBeenCalled()
    const parsed = JSON.parse(consoleErrorSpy.mock.calls[0][0] as string)
    expect(parsed.message).toBe('boom')
  })

  it('omits severity from default-info payload other than the field', () => {
    logEvent('test.default')
    const parsed = JSON.parse(consoleLogSpy.mock.calls[0][0] as string)
    expect(parsed.severity).toBe('info')
  })
})

describe('requestContext', () => {
  const originalSecret = process.env.IRON_SESSION_PASSWORD

  beforeEach(() => {
    process.env.IRON_SESSION_PASSWORD = 'test-only-logger-hmac-secret-at-least-32-chars'
  })

  afterEach(() => {
    if (originalSecret === undefined) delete process.env.IRON_SESSION_PASSWORD
    else process.env.IRON_SESSION_PASSWORD = originalSecret
  })

  function fakeRequest(headers: Record<string, string>, url = 'https://example.com/api/test'): NextRequest {
    const headerMap = new Map(Object.entries(headers).map(([k, v]) => [k.toLowerCase(), v]))
    return {
      method: 'POST',
      url,
      headers: {
        get: (name: string) => headerMap.get(name.toLowerCase()) ?? null,
      },
    } as unknown as NextRequest
  }

  it('daily-HMACs the first forwarded address without logging it raw', () => {
    const req = fakeRequest({ 'x-forwarded-for': '1.2.3.4, 10.0.0.1' })
    const ctx = requestContext(req)
    expect(ctx.client_hash).toMatch(/^h1d:\d{8}:[0-9a-f]{24}$/)
    expect(JSON.stringify(ctx)).not.toContain('1.2.3.4')
  })

  it('omits the client identifier when x-forwarded-for is missing', () => {
    const req = fakeRequest({})
    expect(requestContext(req)).not.toHaveProperty('client_hash')
  })

  it('does not log a user-agent', () => {
    const req = fakeRequest({ 'user-agent': 'identifying-agent-value' })
    const ctx = requestContext(req)
    expect(ctx).not.toHaveProperty('ua')
    expect(JSON.stringify(ctx)).not.toContain('identifying-agent-value')
  })

  it('captures method and path', () => {
    const req = fakeRequest({}, 'https://example.com/api/operator/login?next=/foo')
    const ctx = requestContext(req)
    expect(ctx.method).toBe('POST')
    expect(ctx.path).toBe('/api/operator/login')
  })
})

describe('emailHash', () => {
  const originalSecret = process.env.IRON_SESSION_PASSWORD

  beforeEach(() => {
    process.env.IRON_SESSION_PASSWORD = 'test-only-logger-hmac-secret-at-least-32-chars'
  })

  afterEach(() => {
    vi.useRealTimers()
    if (originalSecret === undefined) delete process.env.IRON_SESSION_PASSWORD
    else process.env.IRON_SESSION_PASSWORD = originalSecret
  })

  it('returns a versioned daily secret-HMAC', async () => {
    const h = await emailHash('user@example.com')
    expect(h).toMatch(/^h1d:\d{8}:[0-9a-f]{24}$/)
  })

  it('is stable only within the same UTC day', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-15T23:59:59Z'))
    const a = await emailHash('user@example.com')
    vi.setSystemTime(new Date('2026-08-15T12:00:00Z'))
    const b = await emailHash('user@example.com')
    expect(a).toBe(b)
    vi.setSystemTime(new Date('2026-08-16T00:00:00Z'))
    const c = await emailHash('user@example.com')
    expect(c).not.toBe(a)
  })

  it('normalizes whitespace and case', async () => {
    const a = await emailHash('user@example.com')
    const b = await emailHash('  User@Example.COM  ')
    expect(a).toBe(b)
  })

  it('different emails produce different hashes', async () => {
    const a = await emailHash('alice@example.com')
    const b = await emailHash('bob@example.com')
    expect(a).not.toBe(b)
  })

  it('omits the identifier when the server secret is unavailable', async () => {
    delete process.env.IRON_SESSION_PASSWORD
    await expect(emailHash('user@example.com')).resolves.toBe('omitted')
  })
})
