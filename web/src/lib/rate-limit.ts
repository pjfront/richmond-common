import { type NextRequest, NextResponse } from 'next/server'
import { getSupabaseAdmin } from './supabase-admin'

// Postgres-backed rate limiter using the check_and_increment_rate_limit RPC
// (migration 106). Counters live in the rate_limit_buckets table; the RPC
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
} as const

export type LimitName = keyof typeof limits

export function clientKey(request: NextRequest, fallback = 'anon'): string {
  const forwarded = request.headers.get('x-forwarded-for')
  const ip = forwarded?.split(',')[0]?.trim()
    || request.headers.get('x-real-ip')
    || fallback
  return ip
}

export interface RateLimitResult {
  allowed: boolean
  response?: Response
}

export async function enforceRateLimit(
  name: LimitName,
  key: string,
): Promise<RateLimitResult> {
  const cfg = limits[name]
  const bucketKey = `${name}:${key}`

  try {
    const supabase = getSupabaseAdmin()
    const { data, error } = await supabase.rpc('check_and_increment_rate_limit', {
      p_bucket_key: bucketKey,
      p_window_secs: cfg.windowSecs,
      p_max_count: cfg.maxCount,
    })

    if (error) {
      console.error(`[rate-limit] RPC error for ${bucketKey}:`, error.message)
      return { allowed: true }
    }

    const row = Array.isArray(data) ? data[0] : data
    if (!row || row.allowed) return { allowed: true }

    const retryAfter = Math.max(0, row.retry_after_secs ?? cfg.windowSecs)
    return {
      allowed: false,
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
    return { allowed: true }
  }
}
