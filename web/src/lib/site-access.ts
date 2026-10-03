import { NextResponse, type NextRequest } from 'next/server'
import { sealData, unsealData } from 'iron-session'

export const SITE_ACCESS_USERNAME = 'richmond'
export const MAX_REVALIDATION_BODY_BYTES = 8192
export const SITE_ACCESS_COOKIE = 'rtp_site_access'
export const SITE_ACCESS_COOKIE_TTL = 60 * 60 * 24 * 7
export const MAX_SITE_ACCESS_BODY_BYTES = 8192

const PRIVATE_HEADERS = {
  'Cache-Control': 'private, no-store',
  'CDN-Cache-Control': 'no-store',
  'Vercel-CDN-Cache-Control': 'no-store',
  'X-Robots-Tag': 'noindex, nofollow',
}

const EMAIL_MACHINE_METHODS = new Map<string, readonly string[]>([
  ['/api/email/send-recap', ['POST']],
  ['/api/email/send-orientation', ['POST']],
  ['/api/email/retry-deliveries', ['POST']],
  ['/api/email/send-digest', ['GET', 'POST']],
])

export function siteAccessRequired(): boolean {
  return process.env.SITE_ACCESS_REQUIRED?.trim().toLowerCase() === 'true'
}

export function getSiteAccessPassword(): string | null {
  const password = process.env.SITE_ACCESS_PASSWORD
  return password && password.length >= 24 && password.length <= 1024 ? password : null
}

/** Never redirect a password form to another origin or back into its POST route. */
export function safeSiteDestination(candidate: string | null | undefined): string {
  if (!candidate?.startsWith('/') || candidate.startsWith('//') || candidate.includes('\\')
    || /[\u0000-\u0020\u007f]/.test(candidate) || /%(?:0[0-9a-f]|1[0-9a-f]|7f)/i.test(candidate)) return '/'
  try {
    const destination = new URL(candidate, 'https://richmondcommons.org')
    if (destination.origin !== 'https://richmondcommons.org'
      || /%2f|%5c/i.test(destination.pathname) || destination.pathname === '/api/site-access') return '/'
    return `${destination.pathname}${destination.search}${destination.hash}`
  } catch { return '/' }
}

async function siteCookieKey(password: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(`richmond-commons-site-access-cookie-v1\0${password}`))
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('')
}

export async function sealSiteAccess(password: string): Promise<string> {
  return sealData({ granted: true, expiresAt: Date.now() + SITE_ACCESS_COOKIE_TTL * 1000 }, {
    password: await siteCookieKey(password), ttl: SITE_ACCESS_COOKIE_TTL,
  })
}

async function hasSiteCookie(request: NextRequest, password: string): Promise<boolean> {
  const cookie = request.cookies.get(SITE_ACCESS_COOKIE)?.value
  if (!cookie || cookie.length > 4096) return false
  try {
    const session = await unsealData<{ granted?: boolean; expiresAt?: number }>(cookie, {
      password: await siteCookieKey(password), ttl: SITE_ACCESS_COOKIE_TTL,
    })
    return session.granted === true && typeof session.expiresAt === 'number' && session.expiresAt > Date.now()
  } catch { return false }
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]!)
}

export function sitePasswordForm(next: string, error?: string): NextResponse {
  const body = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>Richmond Commons</title><style>body{margin:0;background:#f8fafc;color:#17243c;font:17px system-ui,sans-serif}main{max-width:24rem;margin:12vh auto;padding:2rem}h1{font-size:1.7rem}p{line-height:1.5;color:#475569}label{display:block;margin:1.5rem 0 .5rem}input,button{box-sizing:border-box;width:100%;min-height:48px;border-radius:6px;font:inherit}input{border:1px solid #94a3b8;padding:.7rem;background:white}button{margin-top:1rem;background:#17243c;color:white;border:0;cursor:pointer}input:focus-visible,button:focus-visible{outline:3px solid #2563eb;outline-offset:3px}.error{color:#991b1b}</style></head><body><main><h1>Richmond Commons</h1><p>This site is being updated. Enter the password to view it.</p>${error ? `<p class="error" role="alert">${escapeHtml(error)}</p>` : ''}<form action="/api/site-access" method="post"><input type="hidden" name="next" value="${escapeHtml(safeSiteDestination(next))}"><label for="site-password">Password</label><input id="site-password" name="password" type="password" autocomplete="current-password" maxlength="1024" required autofocus><button type="submit">Enter site</button></form></main></body></html>`
  return protectSiteResponse(new NextResponse(body, {
    status: 401,
    headers: { 'Content-Type': 'text/html; charset=utf-8', 'X-Richmond-Site-Access': 'required' },
  }))
}

export function protectSiteResponse<T extends Response>(response: T): T {
  if (siteAccessRequired()) {
    for (const [name, value] of Object.entries(PRIVATE_HEADERS)) response.headers.set(name, value)
  }
  return response
}

/** Compare fixed-size digests with Web Crypto, including in the Edge runtime. */
export async function secretMatches(submitted: string, expected: string | undefined): Promise<boolean> {
  if (!expected || !submitted) return false
  const encoder = new TextEncoder()
  const [submittedDigest, expectedDigest] = await Promise.all([
    crypto.subtle.digest('SHA-256', encoder.encode(submitted)),
    crypto.subtle.digest('SHA-256', encoder.encode(expected)),
  ])
  const actual = new Uint8Array(submittedDigest)
  const wanted = new Uint8Array(expectedDigest)
  let mismatch = 0
  for (let index = 0; index < wanted.length; index++) mismatch |= actual[index] ^ wanted[index]
  return mismatch === 0
}

function basicCredentials(request: NextRequest): string | null {
  const header = request.headers.get('authorization') ?? ''
  if (header.length > 4096) return null
  const match = /^Basic ([A-Za-z0-9+/]+={0,2})$/i.exec(header)
  if (!match) return null
  try {
    const decoded = atob(match[1])
    const bytes = Uint8Array.from(decoded, character => character.charCodeAt(0))
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes)
  } catch {
    return null
  }
}

async function hasMachineBearer(request: NextRequest): Promise<boolean> {
  const header = request.headers.get('authorization') ?? ''
  if (header.length > 4096) return false
  const match = /^Bearer (\S+)$/i.exec(header)
  return Boolean(match && await secretMatches(match[1], process.env.API_SECRET))
}

/** Read a clone so middleware authentication cannot consume a job's request. */
export async function readBoundedRequestText(request: NextRequest, maximum = MAX_REVALIDATION_BODY_BYTES): Promise<string | null> {
  const length = request.headers.get('content-length')
  if (length && (!/^\d+$/.test(length) || Number(length) > maximum)) return null
  const reader = request.clone().body?.getReader()
  if (!reader) return null
  const chunks: Uint8Array[] = []
  let size = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      size += value.byteLength
      if (size > maximum) {
        // A cloned stream tees the original: awaiting cancellation could wait
        // for the downstream consumer, which never runs for a rejected body.
        void reader.cancel().catch(() => {})
        return null
      }
      chunks.push(value)
    }
    const bytes = new Uint8Array(size)
    let offset = 0
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength }
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes)
  } catch {
    return null
  } finally {
    reader.releaseLock()
  }
}

export async function readBoundedRevalidationBody(request: NextRequest): Promise<Record<string, unknown> | null> {
  const text = await readBoundedRequestText(request)
  if (text === null) return null
  try {
    const body: unknown = JSON.parse(text)
    return body && typeof body === 'object' && !Array.isArray(body) ? body as Record<string, unknown> : null
  } catch { return null }
}

/** A response blocks access; null allows the existing route authorization to run. */
export async function siteAccessResponse(request: NextRequest): Promise<NextResponse | null> {
  if (!siteAccessRequired()) return null
  const expected = getSiteAccessPassword()
  if (!expected) {
    return protectSiteResponse(NextResponse.json({ error: 'Site access unavailable' }, { status: 503 }))
  }

  try {
    const path = request.nextUrl.pathname
    // This is the sole public authentication mutation. Its own handler checks
    // the password, same-origin form submission and safe return destination.
    if (path === '/api/site-access' && request.method === 'POST') return null
    if (await hasSiteCookie(request, expected)) return null
    // Retained for bounded authenticated verification; no browser challenge
    // advertises Basic authentication and the visible form has no username.
    const credentials = basicCredentials(request)
    if (credentials && await secretMatches(credentials, `${SITE_ACCESS_USERNAME}:${expected}`)) return null

    const methods = EMAIL_MACHINE_METHODS.get(path)
    if ((methods?.includes(request.method) || (path === '/api/health' && request.method === 'GET'))
      && await hasMachineBearer(request)) return null

    if (path === '/api/revalidate' && request.method === 'POST' && process.env.REVALIDATION_SECRET) {
      const body = await readBoundedRevalidationBody(request)
      if (typeof body?.secret === 'string' && await secretMatches(body.secret, process.env.REVALIDATION_SECRET)) return null
    }

    // Existing email opt-out links remain usable; the handler validates the
    // subscriber token and returns self-contained confirmation HTML only.
    const tokens = request.nextUrl.searchParams.getAll('token')
    if (path === '/api/subscribe' && request.method === 'GET' && tokens.length === 1
      && tokens[0].length > 0 && tokens[0].length <= 200) return null

    // Anonymous monitoring can establish that the gate is serving, without
    // running database probes or exposing schema/source information.
    if (path === '/api/health' && request.method === 'GET') {
      return protectSiteResponse(NextResponse.json({ status: 'protected' }))
    }

    if (path.startsWith('/api/')) {
      return protectSiteResponse(NextResponse.json({ error: 'Site password required' }, { status: 401 }))
    }
    return sitePasswordForm(`${path}${request.nextUrl.search}`)
  } catch {
    return protectSiteResponse(NextResponse.json({ error: 'Site access unavailable' }, { status: 503 }))
  }
}
