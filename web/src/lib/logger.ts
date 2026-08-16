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
 * - Never log raw passwords, emails, request addresses, or user agents.
 *   Resident-linked log pseudonyms rotate daily.
 * - `severity` defaults to 'info'. Use 'warn' for rate limits or
 *   validation rejections, 'error' for unexpected failures.
 *
 * This is intentionally a thin wrapper around console.log. We can
 * layer Sentry or another sink on top later without changing call
 * sites — the contract is "emit a structured event," the transport
 * is replaceable.
 */
import { createHmac } from 'node:crypto'
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

function dailySecretHmac(purpose: string, value: string): string | null {
  const secret = process.env.IRON_SESSION_PASSWORD
  if (!secret || secret.length < 32 || !value) return null

  const utcDay = new Date().toISOString().slice(0, 10).replaceAll('-', '')
  const digest = createHmac('sha256', secret)
    .update(`richmond-commons-log-${purpose}\0`)
    .update(utcDay)
    .update('\0')
    .update(value)
    .digest('hex')

  return `h1d:${utcDay}:${digest.slice(0, 24)}`
}

/** Extract non-identifying operational request context. */
export function requestContext(request: NextRequest): Record<string, string> {
  const fwd = request.headers.get('x-forwarded-for') ?? ''
  const ip = fwd.split(',')[0]?.trim() || 'unknown'
  const clientHash = dailySecretHmac('request-client', ip === 'unknown' ? '' : ip)
  const context: Record<string, string> = {
    method: request.method,
    path: new URL(request.url).pathname,
  }
  if (clientHash) context.client_hash = clientHash
  return context
}

/**
 * Create a daily, secret-keyed email pseudonym for operational correlation.
 * It cannot link an address across UTC days. If the required server secret is
 * unavailable, omit the identifier rather than falling back to a stable hash.
 */
export async function emailHash(email: string): Promise<string> {
  const normalized = email.trim().toLowerCase()
  return dailySecretHmac('email', normalized) ?? 'omitted'
}
