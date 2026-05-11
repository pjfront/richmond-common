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

  it('extracts first IP from comma-separated x-forwarded-for', () => {
    const req = fakeRequest({ 'x-forwarded-for': '1.2.3.4, 10.0.0.1' })
    expect(requestContext(req).ip).toBe('1.2.3.4')
  })

  it('falls back to "unknown" when x-forwarded-for is missing', () => {
    const req = fakeRequest({})
    expect(requestContext(req).ip).toBe('unknown')
  })

  it('truncates user-agent to 120 chars', () => {
    const longUa = 'A'.repeat(500)
    const req = fakeRequest({ 'user-agent': longUa })
    expect(requestContext(req).ua.length).toBe(120)
  })

  it('captures method and path', () => {
    const req = fakeRequest({}, 'https://example.com/api/operator/login?next=/foo')
    const ctx = requestContext(req)
    expect(ctx.method).toBe('POST')
    expect(ctx.path).toBe('/api/operator/login')
  })
})

describe('emailHash', () => {
  it('returns a 12-char lowercase hex string', async () => {
    const h = await emailHash('user@example.com')
    expect(h).toMatch(/^[0-9a-f]{12}$/)
  })

  it('is stable: same email yields same hash', async () => {
    const a = await emailHash('user@example.com')
    const b = await emailHash('user@example.com')
    expect(a).toBe(b)
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
})
