import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'
import { unstable_doesMiddlewareMatch } from 'next/experimental/testing/server'
const mocks = vi.hoisted(() => ({ session: { isOperator: false }, getIronSession: vi.fn() }))
vi.mock('iron-session', () => ({ getIronSession: mocks.getIronSession }))
vi.mock('@/lib/operator-session', () => ({ getOperatorSessionOptions: () => ({ cookieName: 'test', password: 'x'.repeat(32) }) }))
import { config, middleware } from './middleware'

describe('sitewide middleware boundary', () => {
  beforeEach(() => {
    vi.stubEnv('SITE_ACCESS_REQUIRED', 'true')
    vi.stubEnv('SITE_ACCESS_PASSWORD', 'fixture-preview-password')
    mocks.session.isOperator = false
    mocks.getIronSession.mockReset().mockResolvedValue(mocks.session)
  })
  afterEach(() => vi.unstubAllEnvs())
  const basic = `Basic ${btoa('richmond:fixture-preview-password')}`

  it.each(['/', '/meetings/id?_rsc=a', '/api/search', '/api/finance/export', '/_next/static/app.js', '/_next/image', '/_next/data/build/item.json', '/data/a.geojson', '/sitemap.xml'])('matches %s before any content routing', url => {
    expect(unstable_doesMiddlewareMatch({ config, nextConfig: {}, url })).toBe(true)
  })

  it('does not bypass auth for prefetch, RSC, spoofed internal headers or operator cookies', async () => {
    const response = await middleware(new NextRequest('https://richmondcommons.org/meetings/id?_rsc=abc', {
      headers: { RSC: '1', 'next-router-prefetch': '1', purpose: 'prefetch', 'x-middleware-subrequest': 'middleware:middleware:middleware:middleware:middleware', Cookie: 'rtp_operator=fake' },
    }))
    expect(response.status).toBe(401)
    expect(mocks.getIronSession).not.toHaveBeenCalled()
  })

  it('keeps HEAD and POST content requests behind the same challenge', async () => {
    for (const method of ['HEAD', 'POST']) expect((await middleware(new NextRequest('https://richmondcommons.org/', { method }))).status).toBe(401)
  })

  it('allows site access without granting operator privileges', async () => {
    const response = await middleware(new NextRequest('https://richmondcommons.org/operator/settings', { headers: { Authorization: basic } }))
    expect(response.status).toBe(307)
    expect(response.headers.get('Location')).toContain('/operator/login')
    expect(response.headers.get('Cache-Control')).toBe('private, no-store')
    mocks.session.isOperator = true
    const operator = await middleware(new NextRequest('https://richmondcommons.org/operator/settings', { headers: { Authorization: basic } }))
    expect(operator.headers.get('x-middleware-next')).toBe('1')
  })

  it('preserves normal operator sign-in and public routing when the site flag is disabled', async () => {
    vi.stubEnv('SITE_ACCESS_REQUIRED', '')
    const publicResponse = await middleware(new NextRequest('https://richmondcommons.org/'))
    expect(publicResponse.headers.get('x-middleware-next')).toBe('1')
    expect(publicResponse.headers.has('X-Robots-Tag')).toBe(false)
    const operator = await middleware(new NextRequest('https://richmondcommons.org/operator/settings'))
    expect(operator.status).toBe(307)
  })
})
