/**
 * Structured JSON logger for server-side route handlers.
 *
 * Vercel ingests stdout from serverless functions into queryable runtime
 * logs. JSON lines stay greppable for "what mutated this row" questions
 * after the fact — the question the 2026-05-11 audit found we couldn't
 * answer for operator-config mutations because plain console.log lines
 * lost the request context.
 *
 * Usage:
 *   import { logEvent, requestContext } from '@/lib/logger'
 *   logEvent('operator.login.success', { ...requestContext(request) })
 *   logEvent('subscribe.rate_limited', { ...requestContext(request), email_hash })
 *
 * Conventions:
 * - Event names are `<surface>.<action>[.<outcome>]` in dot-snake-case
 *   (e.g., `operator.login.failure`, `subscribe.created`,
 *   `community_comment.flagged`).
 * - Never log raw passwords, full emails, or PII. Hash or truncate.
 * - `severity` defaults to 'info'. Use 'warn' for rate limits or
 *   validation rejections, 'error' for unexpected failures.
 *
 * This is intentionally a thin wrapper around console.log. We can
 * layer Sentry or another sink on top later without changing call
 * sites — the contract is "emit a structured event," the transport
 * is replaceable.
 */
import type { NextRequest } from 'next/server'

export type LogSeverity = 'info' | 'warn' | 'error'

export interface LogFields {
  severity?: LogSeverity
  [key: string]: unknown
}

export function logEvent(event: string, fields: LogFields = {}): void {
  const { severity = 'info', ...rest } = fields
  const payload = {
    ts: new Date().toISOString(),
    severity,
    event,
    ...rest,
  }
  const line = JSON.stringify(payload)
  if (severity === 'error') {
    console.error(line)
  } else if (severity === 'warn') {
    console.warn(line)
  } else {
    console.log(line)
  }
}

/**
 * Extract a stable, privacy-conscious request context dict for log
 * fields. IP comes from the Vercel x-forwarded-for header (most
 * specific entry). User-agent is truncated to keep lines short.
 */
export function requestContext(request: NextRequest): Record<string, string> {
  const fwd = request.headers.get('x-forwarded-for') ?? ''
  const ip = fwd.split(',')[0]?.trim() || 'unknown'
  const ua = (request.headers.get('user-agent') ?? '').slice(0, 120)
  return {
    method: request.method,
    path: new URL(request.url).pathname,
    ip,
    ua,
  }
}

/**
 * Hash an email for log fields. Stable per-email so repeated submissions
 * by the same email line up, but the email itself isn't recoverable from
 * the log. SHA-256 → first 12 hex chars is enough entropy at our volume.
 */
export async function emailHash(email: string): Promise<string> {
  const normalized = email.trim().toLowerCase()
  const buf = new TextEncoder().encode(normalized)
  const digest = await crypto.subtle.digest('SHA-256', buf)
  return Array.from(new Uint8Array(digest))
    .slice(0, 6)
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
}
