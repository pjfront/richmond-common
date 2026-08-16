import { createHmac } from 'node:crypto'
import { type NextRequest, NextResponse } from 'next/server'
import { getSupabaseAdmin } from './supabase-admin'

// Postgres-backed rate limiter using the check_and_increment_rate_limit RPC
// (migration 107). Counters live in the rate_limit_buckets table; the RPC
// quantizes time into fixed windows and bumps the count atomically.
//
// Falls open (allows the request) on RPC failure. Rationale: a Supabase
// blip should not lock users out of subscribe/comments/feedback. The login
// route is the one exception — it gates on its own failure mode and is
// already slow-on-purpose (LOGIN_DELAY_MS).

export interface LimitConfig {
  windowSecs: number
  maxCount: number
}

export const limits = {
  login:      { windowSecs: 15 * 60, maxCount: 5 },
  subscribe:  { windowSecs: 60 * 60, maxCount: 5 },
  comments:   { windowSecs: 60 * 60, maxCount: 10 },
  feedback:   { windowSecs: 60 * 60, maxCount: 10 },
  revalidate: { windowSecs: 60,      maxCount: 60 },
  search:     { windowSecs: 60,      maxCount: 15 },
} as const

export type LimitName = keyof typeof limits

const CLIENT_KEY_VERSION = 'h1d'
const VERSIONED_CLIENT_KEY = /^h1d:\d{8}:[0-9a-f]{64}$/
const NON_IDENTIFYING_FALLBACK = /^[a-z][a-z0-9_-]{0,31}$/
const CLIENT_KEY_RETENTION_MS = 24 * 60 * 60 * 1000
const CLEANUP_RETRY_MS = 5 * 60 * 1000
let nextCleanupAt = 0

function pseudonymizeClientAddress(address: string, fallback: string): string {
  // IRON_SESSION_PASSWORD is already a required, high-entropy, server-only
  // secret. Domain separation keeps these HMACs independent from its session
  // use without introducing another credential to provision or rotate.
  const secret = process.env.IRON_SESSION_PASSWORD
  if (!secret || secret.length < 32) return fallback

  // Every limiter window divides evenly into a UTC day, so a daily salt keeps
  // the per-IP limit stable inside its window without creating a cross-day
  // identifier. Only the HMAC is persisted; the address never reaches logs or
  // Postgres through this module.
  const utcDay = new Date().toISOString().slice(0, 10).replaceAll('-', '')
  const digest = createHmac('sha256', secret)
    .update('richmond-commons-rate-limit-client-key\0')
    .update(utcDay)
    .update('\0')
    .update(address)
    .digest('hex')

  return `${CLIENT_KEY_VERSION}:${utcDay}:${digest}`
}

export function clientKey(request: NextRequest, fallback = 'anon'): string {
  const forwarded = request.headers.get('x-forwarded-for')
  const ip = forwarded?.split(',')[0]?.trim()
    || request.headers.get('x-real-ip')
  if (!ip) return fallback
  return pseudonymizeClientAddress(ip.trim().toLowerCase(), fallback)
}

function storageSafeClientKey(key: string): string {
  const normalized = key.trim()
  if (VERSIONED_CLIENT_KEY.test(normalized)) return normalized
  if (NON_IDENTIFYING_FALLBACK.test(normalized)) return normalized

  // Defense in depth: a future call site that passes an address (or another
  // identifier) directly to enforceRateLimit still cannot persist it raw.
  return pseudonymizeClientAddress(normalized, 'unknown')
}

async function pruneExpiredPseudonymousBuckets(
  supabase: ReturnType<typeof getSupabaseAdmin>,
): Promise<void> {
  const now = Date.now()
  if (now < nextCleanupAt) return

  // Mark the attempt before awaiting so concurrent requests on the same warm
  // runtime do not fan out duplicate cleanup queries. A failed attempt retries
  // after five minutes; a successful one waits a day. Cold runtimes may each
  // issue one bounded query, which is safe and keeps cleanup infrastructure-free.
  nextCleanupAt = now + CLEANUP_RETRY_MS
  try {
    const cutoff = new Date(now - CLIENT_KEY_RETENTION_MS).toISOString()
    const { error } = await supabase
      .from('rate_limit_buckets')
      .delete()
      .lt('window_start', cutoff)
      .like('bucket_key', `%:${CLIENT_KEY_VERSION}:%`)

    if (error) {
      console.error('[rate-limit] pseudonymous bucket cleanup failed:', error.message)
      return
    }
    nextCleanupAt = now + CLIENT_KEY_RETENTION_MS
  } catch (err) {
    console.error('[rate-limit] unexpected pseudonymous bucket cleanup error:', err)
  }
}

export interface RateLimitResult {
  allowed: boolean
  /** False means the request may proceed, but no paid downstream work may. */
  backendAvailable: boolean
  response?: Response
}

export async function enforceRateLimit(
  name: LimitName,
  key: string,
): Promise<RateLimitResult> {
  const cfg = limits[name]
  const bucketKey = `${name}:${storageSafeClientKey(key)}`

  try {
    const supabase = getSupabaseAdmin()
    const { data, error } = await supabase.rpc('check_and_increment_rate_limit', {
      p_bucket_key: bucketKey,
      p_window_secs: cfg.windowSecs,
      p_max_count: cfg.maxCount,
    })

    if (error) {
      console.error(`[rate-limit] RPC error for ${bucketKey}:`, error.message)
      return { allowed: true, backendAvailable: false }
    }

    await pruneExpiredPseudonymousBuckets(supabase)

    const row = Array.isArray(data) ? data[0] : data
    if (!row) return { allowed: true, backendAvailable: false }
    if (row.allowed) return { allowed: true, backendAvailable: true }

    const retryAfter = Math.max(0, row.retry_after_secs ?? cfg.windowSecs)
    return {
      allowed: false,
      backendAvailable: true,
      response: NextResponse.json(
        { error: 'Too many requests. Please try again later.' },
        {
          status: 429,
          headers: {
            'Retry-After': String(retryAfter),
            'X-RateLimit-Limit': String(cfg.maxCount),
          },
        },
      ),
    }
  } catch (err) {
    console.error(`[rate-limit] unexpected error for ${bucketKey}:`, err)
    return { allowed: true, backendAvailable: false }
  }
}
