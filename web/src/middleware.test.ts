import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'
import { unstable_doesMiddlewareMatch } from 'next/experimental/testing/server'
const mocks = vi.hoisted(() => ({ session: { isOperator: false }, getIronSession: vi.fn() }))
vi.mock('iron-session', async importOriginal => ({ ...(await importOriginal<typeof import('iron-session')>()), getIronSession: mocks.getIronSession }))
vi.mock('@/lib/operator-session', () => ({ getOperatorSessionOptions: () => ({ cookieName: 'test', password: 'x'.repeat(32) }) }))
import { config, middleware } from './middleware'
import { sealSiteAccess, SITE_ACCESS_COOKIE } from '@/lib/site-access'
import * as featurePolicy from '@/lib/feature-policy'

describe('sitewide middleware boundary', () => {
  beforeEach(() => {
    // Exercise the existing password/session layer independently of tiers.
    vi.spyOn(featurePolicy, 'featureRouteAllowed').mockReturnValue(true)
    vi.stubEnv('SITE_ACCESS_REQUIRED', 'true')
    vi.stubEnv('SITE_ACCESS_PASSWORD', 'fixture-preview-password')
    vi.stubEnv('RICHMOND_READ_ONLY_STAGE', 'false')
    mocks.session.isOperator = false
    mocks.getIronSession.mockReset().mockResolvedValue(mocks.session)
  })
  afterEach(() => { vi.unstubAllEnvs(); vi.restoreAllMocks() })
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

describe('local runtime boundary before authentication', () => {
  beforeEach(() => {
    vi.stubEnv('VERCEL', '')
    vi.stubEnv('RICHMOND_LOCAL_ARCHIVE', 'true')
    vi.stubEnv('RICHMOND_FEATURE_PROFILE', 'local_archive')
    vi.stubEnv('RICHMOND_READ_ONLY_STAGE', 'false')
    vi.stubEnv('SITE_ACCESS_REQUIRED', 'false')
  })
  afterEach(() => vi.unstubAllEnvs())
  it('allows local reads and blocks foreign origins, cloud hosts, and writes', async () => {
    expect((await middleware(new NextRequest('http://127.0.0.1:3100/council'))).headers.get('x-middleware-next')).toBe('1')
    expect((await middleware(new NextRequest('http://127.0.0.1:3100/council', { headers: { Origin: 'https://attacker.example' } }))).status).toBe(403)
    expect((await middleware(new NextRequest('https://richmondcommons.org/council'))).status).toBe(403)
    expect((await middleware(new NextRequest('http://127.0.0.1:3100/api/operator/settings', { method: 'PUT' }))).status).toBe(404)
    expect((await middleware(new NextRequest('http://127.0.0.1:3100/api/email/send-digest'))).status).toBe(404)
  })
})

describe('read-only stage before every authentication exception', () => {
  const password = 'fixture-preview-password'
  beforeEach(() => {
    vi.stubEnv('RICHMOND_READ_ONLY_STAGE', 'true')
    vi.stubEnv('SITE_ACCESS_REQUIRED', 'true')
    vi.stubEnv('SITE_ACCESS_PASSWORD', password)
    vi.stubEnv('API_SECRET', 'fixture-machine-service-secret')
    vi.stubEnv('REVALIDATION_SECRET', 'fixture-revalidation-secret')
    mocks.getIronSession.mockReset().mockResolvedValue({ isOperator: true })
  })
  afterEach(() => vi.unstubAllEnvs())

  it.each([
    ['POST', '/'], ['POST', '/meetings/id'], ['POST', '/api/commons/search'],
    ['POST', '/api/email/send-recap'], ['POST', '/api/email/send-digest'], ['GET', '/api/email/send-digest'],
    ['POST', '/api/revalidate'], ['GET', '/api/health'], ['GET', '/api/subscribe?token=fixture'],
    ['GET', '/operator'], ['GET', '/api/operator/session'], ['GET', '/api/site-access'],
  ])('denies %s %s despite valid site, operator and service credentials', async (method, path) => {
    const cookie = await sealSiteAccess(password)
    const response = await middleware(new NextRequest(`https://richmondcommons.org${path}`, {
      method, headers: { Cookie: `${SITE_ACCESS_COOKIE}=${cookie}; rtp_operator=fixture`,
        Authorization: 'Bearer fixture-machine-service-secret', Origin: 'https://richmondcommons.org', 'Content-Type': 'application/json' },
      ...(method === 'POST' ? { body: JSON.stringify({ secret: 'fixture-revalidation-secret' }) } : {}),
    }))
    expect(response.status).toBe(404)
    expect(response.headers.get('Cache-Control')).toBe('private, no-store')
    expect(response.headers.get('X-Robots-Tag')).toBe('noindex, nofollow')
    expect(mocks.getIronSession).not.toHaveBeenCalled()
  })

  it('cannot use scripted Basic access to reopen a denied mutation', async () => {
    const response = await middleware(new NextRequest('https://richmondcommons.org/api/revalidate', {
      method: 'POST', headers: { Authorization: `Basic ${btoa(`richmond:${password}`)}` },
      body: JSON.stringify({ secret: 'fixture-revalidation-secret' }),
    }))
    expect(response.status).toBe(404)
  })

  it('allows the exact password-cookie POST to reach its independent same-origin handler', async () => {
    const response = await middleware(new NextRequest('https://richmondcommons.org/api/site-access', {
      method: 'POST', headers: { Origin: 'https://richmondcommons.org', 'Content-Type': 'application/x-www-form-urlencoded' },
      body: 'password=not-yet-authenticated',
    }))
    expect(response.headers.get('x-middleware-next')).toBe('1')
    expect(response.headers.get('Cache-Control')).toBe('private, no-store')
  })

  it('requires the password for allowed reads and permits them with the separate site cookie', async () => {
    const anonymous = await middleware(new NextRequest('https://richmondcommons.org/search?q=housing'))
    expect(anonymous.status).toBe(401)
    expect(anonymous.headers.has('WWW-Authenticate')).toBe(false)
    const cookie = await sealSiteAccess(password)
    for (const path of ['/search?q=housing', '/api/commons/search?q=housing', '/api/finance/export?q=housing', '/_next/static/chunks/app.js']) {
      const response = await middleware(new NextRequest(`https://richmondcommons.org${path}`, { headers: { Cookie: `${SITE_ACCESS_COOKIE}=${cookie}` } }))
      expect(response.headers.get('x-middleware-next')).toBe('1')
      expect(response.headers.get('Vercel-CDN-Cache-Control')).toBe('no-store')
    }
    expect(mocks.getIronSession).not.toHaveBeenCalled()
  })
})
