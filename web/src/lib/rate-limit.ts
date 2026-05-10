import { Ratelimit } from '@upstash/ratelimit'
import { Redis } from '@upstash/redis'
import { type NextRequest, NextResponse } from 'next/server'

const url = process.env.UPSTASH_REDIS_REST_URL
const token = process.env.UPSTASH_REDIS_REST_TOKEN

const redis = url && token ? new Redis({ url, token }) : null

if (!redis && process.env.NODE_ENV === 'production') {
  console.warn(
    '[rate-limit] UPSTASH_REDIS_REST_URL/TOKEN not set — rate limiting disabled in production. THIS IS A SECURITY HAZARD.',
  )
}

type Window = `${number} ${'s' | 'm' | 'h' | 'd'}`

function makeLimiter(prefix: string, limit: number, window: Window) {
  if (!redis) return null
  return new Ratelimit({
    redis,
    limiter: Ratelimit.slidingWindow(limit, window),
    analytics: false,
    prefix: `rtp:${prefix}`,
  })
}

export const limiters = {
  login: makeLimiter('login', 5, '15 m'),
  subscribe: makeLimiter('subscribe', 5, '1 h'),
  comments: makeLimiter('comments', 10, '1 h'),
  feedback: makeLimiter('feedback', 10, '1 h'),
  revalidate: makeLimiter('revalidate', 60, '1 m'),
}

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
  limiter: Ratelimit | null,
  key: string,
): Promise<RateLimitResult> {
  if (!limiter) return { allowed: true }
  const { success, limit, remaining, reset } = await limiter.limit(key)
  if (success) return { allowed: true }
  const resetSeconds = Math.max(0, Math.ceil((reset - Date.now()) / 1000))
  return {
    allowed: false,
    response: NextResponse.json(
      { error: 'Too many requests. Please try again later.' },
      {
        status: 429,
        headers: {
          'Retry-After': String(resetSeconds),
          'X-RateLimit-Limit': String(limit),
          'X-RateLimit-Remaining': String(remaining),
        },
      },
    ),
  }
}
