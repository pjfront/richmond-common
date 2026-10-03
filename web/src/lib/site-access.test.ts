import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { NextRequest, NextResponse } from 'next/server'
import { MAX_REVALIDATION_BODY_BYTES, protectSiteResponse, readBoundedRevalidationBody, sealSiteAccess, secretMatches, SITE_ACCESS_COOKIE, SITE_ACCESS_COOKIE_TTL, siteAccessResponse, sitePasswordForm } from './site-access'

const password = 'test-preview-password-keep-server-only'
const basic = (user = 'richmond', pass = password) => `Basic ${btoa(`${user}:${pass}`)}`
function request(path: string, authorization?: string, method = 'GET', body?: object) {
  return new NextRequest(`https://richmondcommons.org${path}`, {
    method,
    headers: { ...(authorization ? { Authorization: authorization } : {}), ...(body ? { 'Content-Type': 'application/json' } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}),
  })
}

describe('private site access', () => {
  beforeEach(() => {
    vi.stubEnv('SITE_ACCESS_REQUIRED', 'true')
    vi.stubEnv('SITE_ACCESS_PASSWORD', password)
    vi.stubEnv('API_SECRET', 'machine-secret')
    vi.stubEnv('REVALIDATION_SECRET', 'revalidation-secret')
  })
  afterEach(() => { vi.unstubAllEnvs(); vi.useRealTimers() })

  it('leaves existing previews and local builds unchanged without explicit activation', async () => {
    vi.stubEnv('SITE_ACCESS_REQUIRED', '')
    vi.stubEnv('SITE_ACCESS_PASSWORD', '')
    expect(await siteAccessResponse(request('/'))).toBeNull()
    expect(protectSiteResponse(NextResponse.next()).headers.has('X-Robots-Tag')).toBe(false)
  })

  it('fails closed even for monitoring and jobs when the required password is missing', async () => {
    vi.stubEnv('SITE_ACCESS_PASSWORD', '')
    for (const path of ['/', '/api/health', '/api/email/send-digest']) {
      const response = await siteAccessResponse(request(path, 'Bearer machine-secret'))
      expect(response?.status).toBe(503)
      expect(response?.headers.get('Cache-Control')).toBe('private, no-store')
      expect(response?.headers.get('X-Robots-Tag')).toBe('noindex, nofollow')
    }
  })

  it.each([1, 23])('rejects a configured password of only %s characters even when supplied correctly', async length => {
    const short = 'x'.repeat(length)
    vi.stubEnv('SITE_ACCESS_PASSWORD', short)
    const response = await siteAccessResponse(request('/', basic('richmond', short)))
    expect(response?.status).toBe(503)
    expect(response?.headers.get('Cache-Control')).toBe('private, no-store')
    expect(await response?.text()).not.toContain(short)
  })

  it.each(['/', '/search?q=housing', '/meetings/id/items/A.1?_rsc=abc', '/api/search?q=housing', '/api/finance/export', '/sitemap.xml', '/robots.txt', '/_next/static/chunk.js', '/_next/image?url=%2Fdata.png&w=100&q=75', '/_next/data/build/meeting.json', '/data/richmond-districts.geojson'])('protects %s with a noncacheable challenge', async path => {
    const response = await siteAccessResponse(request(path))
    expect(response?.status).toBe(401)
    expect(response?.headers.has('WWW-Authenticate')).toBe(false)
    if (!path.startsWith('/api/')) expect(response?.headers.get('X-Richmond-Site-Access')).toBe('required')
    expect(response?.headers.get('Cache-Control')).toBe('private, no-store')
    expect(response?.headers.get('Vercel-CDN-Cache-Control')).toBe('no-store')
    expect(response?.headers.get('X-Robots-Tag')).toBe('noindex, nofollow')
    expect(await response?.text()).not.toContain(password)
  })

  it('requires the fixed username and exact password; malformed headers fail safely', async () => {
    for (const header of [basic('other'), basic('richmond', 'wrong'), 'Basic !invalid!', 'Basic ', 'Bearer machine-secret', 'Basic ' + 'A'.repeat(5000)]) {
      expect((await siteAccessResponse(request('/', header)))?.status).toBe(401)
    }
    expect(await siteAccessResponse(request('/', basic()))).toBeNull()
    expect(await secretMatches('short', 'much-longer')).toBe(false)
    expect(await secretMatches('secret', undefined)).toBe(false)
    expect(await secretMatches('secret', 'secret')).toBe(true)
  })

  it('shows only a self-contained password form without a username or external sign-in', async () => {
    const response = await siteAccessResponse(request('/meetings/id?q=housing'))
    const html = await response!.text()
    expect(html).toContain('action="/api/site-access"')
    expect(html).toContain('name="password" type="password" autocomplete="current-password"')
    expect(html).toContain('name="next" value="/meetings/id?q=housing"')
    expect(html).not.toMatch(/name="username"|WWW-Authenticate|<script|<link|https:\/\//)
    expect(response?.headers.has('WWW-Authenticate')).toBe(false)
    expect((await siteAccessResponse(request('/api/site-access')))?.status).toBe(401)
    expect(await siteAccessResponse(request('/api/site-access', undefined, 'POST'))).toBeNull()
  })

  it('authenticates a separate sealed cookie and rejects tampering, expiry and password rotation', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-03T12:00:00Z'))
    const seal = await sealSiteAccess(password)
    const make = (value: string) => new NextRequest('https://richmondcommons.org/meetings/id', { headers: { Cookie: `${SITE_ACCESS_COOKIE}=${value}` } })
    expect(await siteAccessResponse(make(seal))).toBeNull()
    const tampered = `${seal.slice(0, 80)}${seal[80] === 'A' ? 'B' : 'A'}${seal.slice(81)}`
    expect((await siteAccessResponse(make(tampered)))?.status).toBe(401)
    expect((await siteAccessResponse(make('fake-cookie')))!.status).toBe(401)
    vi.stubEnv('SITE_ACCESS_PASSWORD', 'rotated-private-preview-password')
    expect((await siteAccessResponse(make(seal)))?.status).toBe(401)
    vi.stubEnv('SITE_ACCESS_PASSWORD', password)
    vi.setSystemTime(new Date(Date.now() + (SITE_ACCESS_COOKIE_TTL + 1) * 1000))
    expect((await siteAccessResponse(make(seal)))?.status).toBe(401)
  })

  it('escapes reflected values and never inserts submitted passwords into the form', async () => {
    const response = sitePasswordForm('/?q=<img>', '<img src=x onerror=alert(1)>')
    const html = await response.text()
    expect(html).not.toContain('<img')
    expect(html).toContain('&lt;img')
  })

  it.each([
    ['/api/email/send-recap', 'POST'], ['/api/email/send-orientation', 'POST'],
    ['/api/email/retry-deliveries', 'POST'], ['/api/email/send-digest', 'GET'],
    ['/api/email/send-digest', 'POST'], ['/api/health', 'GET'],
  ])('preserves authenticated machine access to %s %s', async (path, method) => {
    expect(await siteAccessResponse(request(path, 'Bearer machine-secret', method))).toBeNull()
  })

  it('does not turn a machine secret or URL prefix into a general site bypass', async () => {
    for (const [path, method] of [['/api/email/send-recap', 'GET'], ['/api/email/send-digest/extra', 'POST'], ['/api/search', 'GET'], ['/api/health', 'POST']]) {
      expect((await siteAccessResponse(request(path, 'Bearer machine-secret', method)))?.status).toBe(401)
    }
    expect((await siteAccessResponse(request('/api/email/send-digest', 'Bearer wrong')))?.status).toBe(401)
    vi.stubEnv('API_SECRET', '')
    expect((await siteAccessResponse(request('/api/email/send-digest', 'Bearer machine-secret')))?.status).toBe(401)
  })

  it('provides only a synthetic protected status to anonymous health probes', async () => {
    const response = await siteAccessResponse(request('/api/health'))
    expect(response?.status).toBe(200)
    expect(await response?.json()).toEqual({ status: 'protected' })
    expect(response?.headers.get('Cache-Control')).toBe('private, no-store')
    expect(await siteAccessResponse(request('/api/health', basic()))).toBeNull()
  })

  it('authenticates revalidation from a bounded clone without consuming the job body', async () => {
    const body = { all: true, secret: 'revalidation-secret' }
    const job = request('/api/revalidate', undefined, 'POST', body)
    expect(await siteAccessResponse(job)).toBeNull()
    expect(await job.json()).toEqual(body)
    expect((await siteAccessResponse(request('/api/revalidate', undefined, 'POST', { all: true, secret: 'wrong' })))?.status).toBe(401)
    vi.stubEnv('REVALIDATION_SECRET', '')
    expect((await siteAccessResponse(request('/api/revalidate', undefined, 'POST', body)))?.status).toBe(401)
  })

  it('bounds revalidation by actual bytes even without a content-length header', async () => {
    const large = request('/api/revalidate', undefined, 'POST', { secret: 'revalidation-secret', padding: 'x'.repeat(MAX_REVALIDATION_BODY_BYTES) })
    expect(await readBoundedRevalidationBody(large)).toBeNull()
    expect((await siteAccessResponse(large))?.status).toBe(401)
    const declaredLarge = request('/api/revalidate', undefined, 'POST', { all: true })
    declaredLarge.headers.set('content-length', String(MAX_REVALIDATION_BODY_BYTES + 1))
    expect(await readBoundedRevalidationBody(declaredLarge)).toBeNull()
  })

  it('keeps only the tokenized GET unsubscribe route available to its token validator', async () => {
    expect(await siteAccessResponse(request('/api/subscribe?token=subscriber-token'))).toBeNull()
    for (const path of ['/api/subscribe', '/api/subscribe?token=', '/api/subscribe?token=a&token=b', '/api/subscribe/preferences?token=a', '/subscribe/manage?token=a']) {
      expect((await siteAccessResponse(request(path)))?.status).toBe(401)
    }
    expect((await siteAccessResponse(request('/api/subscribe?token=a', undefined, 'POST')))?.status).toBe(401)
  })

  it('disables caching and indexing for successful authenticated responses too', () => {
    const response = protectSiteResponse(NextResponse.next())
    expect(response.headers.get('Cache-Control')).toBe('private, no-store')
    expect(response.headers.get('CDN-Cache-Control')).toBe('no-store')
    expect(response.headers.get('X-Robots-Tag')).toBe('noindex, nofollow')
  })
})
