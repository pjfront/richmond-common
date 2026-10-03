import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'
import { POST } from './route'
import { MAX_SITE_ACCESS_BODY_BYTES, SITE_ACCESS_COOKIE, SITE_ACCESS_COOKIE_TTL, safeSiteDestination, siteAccessResponse } from '@/lib/site-access'

const password = 'fixture-custom-site-password-only'
function request(fields: Record<string, string> = {}, origin: string | null = 'https://richmondcommons.org') {
  return new NextRequest('https://richmondcommons.org/api/site-access', {
    method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded', ...(origin ? { Origin: origin } : {}) },
    body: new URLSearchParams({ password, next: '/meetings/id?q=housing', ...fields }).toString(),
  })
}

describe('password-only site sign-in', () => {
  beforeEach(() => {
    vi.stubEnv('SITE_ACCESS_REQUIRED', 'true')
    vi.stubEnv('SITE_ACCESS_PASSWORD', password)
    vi.stubEnv('NODE_ENV', 'production')
  })
  afterEach(() => vi.unstubAllEnvs())

  it('sets only the separate sealed seven-day secure cookie and redirects back with 303', async () => {
    const response = await POST(request())
    expect(response.status).toBe(303)
    expect(response.headers.get('Location')).toBe('https://richmondcommons.org/meetings/id?q=housing')
    expect(response.headers.get('Cache-Control')).toBe('private, no-store')
    expect(response.headers.get('X-Robots-Tag')).toBe('noindex, nofollow')
    const header = response.headers.get('Set-Cookie')!
    expect(header).toContain(`${SITE_ACCESS_COOKIE}=`)
    expect(header).toContain(`Max-Age=${SITE_ACCESS_COOKIE_TTL}`)
    expect(header).toContain('HttpOnly')
    expect(header).toContain('Secure')
    expect(header.toLowerCase()).toContain('samesite=strict')
    expect(header).toContain('Path=/')
    expect(header).not.toContain(password)
    expect(header).not.toContain('rtp_operator')
    const cookie = response.cookies.get(SITE_ACCESS_COOKIE)!.value
    expect(await siteAccessResponse(new NextRequest('https://richmondcommons.org/meetings/id', {
      headers: { Cookie: `${SITE_ACCESS_COOKIE}=${cookie}` },
    }))).toBeNull()
  })

  it('returns a password form on a wrong password, with no cookie or browser auth prompt', async () => {
    const response = await POST(request({ password: 'wrong-password' }))
    expect(response.status).toBe(401)
    expect(response.headers.has('Set-Cookie')).toBe(false)
    expect(response.headers.has('WWW-Authenticate')).toBe(false)
    const html = await response.text()
    expect(html).toContain('That password did not work')
    expect(html).toContain('type="password"')
    expect(html).not.toContain('wrong-password')
  })

  it.each([null, 'null', 'https://attacker.example', 'http://richmondcommons.org'])('refuses cross-origin or absent origin %s without setting a cookie', async origin => {
    const response = await POST(request({}, origin))
    expect(response.status).toBe(403)
    expect(response.headers.has('Set-Cookie')).toBe(false)
  })

  it.each(['https://attacker.example/', '//attacker.example/', '/\\attacker.example', '/%2f%2fattacker.example', '/%5cattacker.example', '/x%0d%0aLocation:x', '/api/site-access'])('cannot redirect to unsafe destination %s', async next => {
    expect(safeSiteDestination(next)).toBe('/')
    const response = await POST(request({ next }))
    expect(response.headers.get('Location')).toBe('https://richmondcommons.org/')
  })

  it('fails closed on missing/short secrets and when the hold is disabled', async () => {
    for (const secret of ['', 'too-short']) {
      vi.stubEnv('SITE_ACCESS_PASSWORD', secret)
      expect((await POST(request())).status).toBe(503)
    }
    vi.stubEnv('SITE_ACCESS_REQUIRED', '')
    expect((await POST(request())).status).toBe(404)
  })

  it('rejects oversized bodies, duplicate credentials and non-form submissions', async () => {
    const large = request({ password: 'x'.repeat(MAX_SITE_ACCESS_BODY_BYTES) })
    expect((await POST(large)).status).toBe(400)
    const duplicate = request()
    const malformed = new NextRequest(duplicate.url, {
      method: 'POST', headers: duplicate.headers,
      body: `password=a&password=b`,
    })
    expect((await POST(malformed)).status).toBe(400)
    const json = request()
    json.headers.set('Content-Type', 'application/json')
    expect((await POST(json)).status).toBe(400)
  })
})
