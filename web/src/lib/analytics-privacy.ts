import type { BeforeSendEvent } from '@vercel/analytics'

const PRIVATE_PATHS = ['/operator', '/subscribe/manage'] as const

/** Wait for the session probe and suppress the entire operator browsing session. */
export function shouldMountAnalytics(
  isOperatorResolved: boolean,
  isOperator: boolean,
): boolean {
  return isOperatorResolved && !isOperator
}

/**
 * Keep analytics aggregate-only: private routes are never sent, while every
 * public route is reduced to its pathname before it leaves the browser.
 */
export function sanitizeAnalyticsEvent(
  event: BeforeSendEvent,
): BeforeSendEvent | null {
  // S29 measures aggregate page demand only. If custom-event instrumentation
  // is added elsewhere later, this boundary prevents it from being collected.
  if (event.type !== 'pageview') return null

  const url = new URL(event.url)
  const isPrivate = PRIVATE_PATHS.some(
    (path) => url.pathname === path || url.pathname.startsWith(`${path}/`),
  )

  if (isPrivate) return null

  url.search = ''
  url.hash = ''

  return {
    ...event,
    url: url.toString(),
  }
}
