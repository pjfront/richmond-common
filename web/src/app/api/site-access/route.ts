import { NextResponse, type NextRequest } from 'next/server'
import {
  getSiteAccessPassword, MAX_SITE_ACCESS_BODY_BYTES, protectSiteResponse,
  readBoundedRequestText, safeSiteDestination, sealSiteAccess, secretMatches,
  SITE_ACCESS_COOKIE, SITE_ACCESS_COOKIE_TTL, siteAccessRequired, sitePasswordForm,
} from '@/lib/site-access'

/** Password-only site access: no accounts, operator rights, or database writes. */
export async function POST(request: NextRequest) {
  if (!siteAccessRequired()) return new NextResponse(null, { status: 404 })
  const expected = getSiteAccessPassword()
  if (!expected) return protectSiteResponse(NextResponse.json({ error: 'Site access unavailable' }, { status: 503 }))
  if (request.headers.get('origin') !== request.nextUrl.origin) {
    return protectSiteResponse(NextResponse.json({ error: 'Invalid request origin' }, { status: 403 }))
  }
  if (request.headers.get('content-type')?.split(';')[0].trim().toLowerCase() !== 'application/x-www-form-urlencoded') {
    return protectSiteResponse(NextResponse.json({ error: 'Invalid form' }, { status: 400 }))
  }
  const text = await readBoundedRequestText(request, MAX_SITE_ACCESS_BODY_BYTES)
  if (text === null) return protectSiteResponse(NextResponse.json({ error: 'Invalid form' }, { status: 400 }))
  const form = new URLSearchParams(text)
  const passwords = form.getAll('password')
  const nextValues = form.getAll('next')
  if (passwords.length !== 1 || nextValues.length > 1 || passwords[0].length > 1024) {
    return protectSiteResponse(NextResponse.json({ error: 'Invalid form' }, { status: 400 }))
  }
  const destination = safeSiteDestination(nextValues[0])
  try {
    if (!await secretMatches(passwords[0], expected)) {
      return sitePasswordForm(destination, 'That password did not work. Please try again.')
    }
    const cookie = await sealSiteAccess(expected)
    const response = protectSiteResponse(NextResponse.redirect(new URL(destination, request.url), 303))
    response.cookies.set(SITE_ACCESS_COOKIE, cookie, {
      httpOnly: true, secure: process.env.NODE_ENV === 'production', sameSite: 'strict',
      path: '/', maxAge: SITE_ACCESS_COOKIE_TTL,
    })
    return response
  } catch {
    return protectSiteResponse(NextResponse.json({ error: 'Site access unavailable' }, { status: 503 }))
  }
}
