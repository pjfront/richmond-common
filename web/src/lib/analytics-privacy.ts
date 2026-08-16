import type { BeforeSendEvent } from '@vercel/analytics'

const PRIVATE_PATHS = ['/operator', '/subscribe/manage'] as const
const TOKEN_PARAMETER = /(^|_)(token|secret)($|_)/i

function isPrivatePath(pathname: string): boolean {
  return PRIVATE_PATHS.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  )
}

/** Wait for a successful session probe and suppress the entire operator session. */
export function shouldMountAnalytics(
  isOperatorResolved: boolean,
  isOperator: boolean,
): boolean {
  return isOperatorResolved && !isOperator
}

/**
 * Referrers can contain same-origin management URLs even when the destination
 * page itself is public. Drop that page view instead of transmitting a token.
 */
export function isSensitiveReferrer(referrer: string): boolean {
  if (!referrer) return false

  try {
    const url = new URL(referrer)
    if (isPrivatePath(url.pathname)) return true

    return [...url.searchParams.keys()].some((key) => TOKEN_PARAMETER.test(key))
  } catch {
    // Browser referrers should be absolute URLs. Fail closed if that contract
    // changes so an unparseable value cannot cross the analytics boundary.
    return true
  }
}

/**
 * Keep analytics aggregate-only: private routes and token referrers are never
 * sent, while every public page view is reduced to its pathname.
 */
export function sanitizeAnalyticsEvent(
  event: BeforeSendEvent,
  referrer = '',
): BeforeSendEvent | null {
  // If custom-event instrumentation is added elsewhere later, this boundary
  // prevents the browser analytics component from collecting it.
  if (event.type !== 'pageview' || isSensitiveReferrer(referrer)) return null

  let url: URL
  try {
    url = new URL(event.url)
  } catch {
    return null
  }

  if (isPrivatePath(url.pathname)) return null

  url.search = ''
  url.hash = ''

  return {
    ...event,
    url: url.toString(),
  }
}
