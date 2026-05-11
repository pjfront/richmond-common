import { NextResponse, type NextRequest } from 'next/server'
import { getOperatorSession } from '@/lib/operator-auth'
import { clientKey, enforceRateLimit } from '@/lib/rate-limit'
import { logEvent, requestContext } from '@/lib/logger'

const LOGIN_DELAY_MS = 750

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false
  let mismatch = 0
  for (let i = 0; i < a.length; i++) {
    mismatch |= a.charCodeAt(i) ^ b.charCodeAt(i)
  }
  return mismatch === 0
}

export async function POST(request: NextRequest) {
  const ctx = requestContext(request)
  const expected = process.env.OPERATOR_PASSWORD
  if (!expected) {
    logEvent('operator.login.misconfigured', { ...ctx, severity: 'error' })
    return NextResponse.json({ error: 'Login disabled' }, { status: 503 })
  }

  const limit = await enforceRateLimit('login', clientKey(request))
  if (!limit.allowed) {
    logEvent('operator.login.rate_limited', { ...ctx, severity: 'warn' })
    return limit.response!
  }

  let body: { password?: unknown }
  try {
    body = await request.json()
  } catch {
    logEvent('operator.login.bad_request', { ...ctx, severity: 'warn' })
    return NextResponse.json({ error: 'Invalid request' }, { status: 400 })
  }

  const submitted = typeof body.password === 'string' ? body.password : ''

  await new Promise((resolve) => setTimeout(resolve, LOGIN_DELAY_MS))

  if (!timingSafeEqual(submitted, expected)) {
    logEvent('operator.login.failure', { ...ctx, severity: 'warn' })
    return NextResponse.json({ error: 'Invalid password' }, { status: 401 })
  }

  const session = await getOperatorSession()
  session.isOperator = true
  session.loginAt = Date.now()
  await session.save()

  logEvent('operator.login.success', { ...ctx })
  return NextResponse.json({ ok: true })
}
