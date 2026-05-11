import { describe, it, expect } from 'vitest'
import type { NextRequest } from 'next/server'
import { clientKey, limits } from './rate-limit'

function fakeRequest(headers: Record<string, string>): NextRequest {
  const headerMap = new Map(Object.entries(headers).map(([k, v]) => [k.toLowerCase(), v]))
  return {
    headers: {
      get: (name: string) => headerMap.get(name.toLowerCase()) ?? null,
    },
  } as unknown as NextRequest
}

describe('clientKey', () => {
  it('returns first IP from x-forwarded-for', () => {
    const req = fakeRequest({ 'x-forwarded-for': '203.0.113.5, 10.0.0.1' })
    expect(clientKey(req)).toBe('203.0.113.5')
  })

  it('falls back to x-real-ip when forwarded-for is missing', () => {
    const req = fakeRequest({ 'x-real-ip': '198.51.100.7' })
    expect(clientKey(req)).toBe('198.51.100.7')
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
    const req = fakeRequest({ 'x-forwarded-for': '   192.0.2.1   , 10.0.0.1' })
    expect(clientKey(req)).toBe('192.0.2.1')
  })
})

describe('limits config', () => {
  it('has all five expected buckets', () => {
    expect(Object.keys(limits).sort()).toEqual(
      ['comments', 'feedback', 'login', 'revalidate', 'subscribe'],
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
})
