import { NextRequest, NextResponse } from 'next/server'
import { getSupabaseAdmin } from '@/lib/supabase-admin'
import { sendEmail, buildWelcomeEmail } from '@/lib/email'
import type { SubscribeResponse, EmailSubscriber } from '@/lib/types'

const RICHMOND_FIPS = '0660620'
const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://richmondcommons.org'

// ─── Rate Limiting ──────────────────────────────────────────

const ipRequests = new Map<string, number[]>()
const IP_LIMIT = 5
const IP_WINDOW_MS = 60 * 60 * 1000 // 1 hour

function checkRateLimit(ip: string): string | null {
  const now = Date.now()
  const times = ipRequests.get(ip) ?? []
  const recent = times.filter((t) => now - t < IP_WINDOW_MS)
  if (recent.length >= IP_LIMIT) {
    return 'Too many requests. Please try again later.'
  }
  recent.push(now)
  ipRequests.set(ip, recent)
  return null
}

// ─── Validation ─────────────────────────────────────────────

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function validateEmail(email: unknown): string | null {
  if (typeof email !== 'string' || !EMAIL_RE.test(email)) {
    return 'Please enter a valid email address.'
  }
  if (email.length > 255) {
    return 'Email address is too long.'
  }
  return null
}

// ─── POST: Subscribe ────────────────────────────────────────

export async function POST(request: NextRequest) {
  try {
    const ip =
      request.headers.get('x-forwarded-for')?.split(',')[0]?.trim() ??
      request.headers.get('x-real-ip') ??
      'unknown'

    const rateLimitError = checkRateLimit(ip)
    if (rateLimitError) {
      return NextResponse.json(
        { success: false, message: rateLimitError } satisfies SubscribeResponse,
        { status: 429 },
      )
    }

    const body = await request.json() as Record<string, unknown>
    const email = (typeof body.email === 'string' ? body.email : '').toLowerCase().trim()
    const name = typeof body.name === 'string' ? body.name.trim().slice(0, 200) || null : null

    const emailError = validateEmail(email)
    if (emailError) {
      return NextResponse.json(
        { success: false, message: emailError } satisfies SubscribeResponse,
        { status: 400 },
      )
    }

    const supabase = getSupabaseAdmin()

    // Check if already exists
    const { data: existing } = await supabase
      .from('email_subscribers')
      .select('id, name, status, unsubscribe_token')
      .eq('email', email)
      .single() as { data: Pick<EmailSubscriber, 'id' | 'name' | 'status' | 'unsubscribe_token'> | null; error: unknown }

    if (existing && existing.status === 'active') {
      return NextResponse.json(
        { success: true, message: 'You\'re already subscribed!', already_subscribed: true } satisfies SubscribeResponse,
        { status: 200 },
      )
    }

    let unsubscribeToken: string

    if (existing) {
      // Re-subscribe: was previously unsubscribed
      const { error } = await supabase
        .from('email_subscribers')
        .update({
          status: 'active',
          name: name ?? existing.name, // keep existing name if not provided
          subscribed_at: new Date().toISOString(),
          unsubscribed_at: null,
        })
        .eq('id', existing.id)

      if (error) {
        console.error('Re-subscribe error:', error)
        return NextResponse.json(
          { success: false, message: 'Something went wrong. Please try again.' } satisfies SubscribeResponse,
          { status: 500 },
        )
      }
      unsubscribeToken = existing.unsubscribe_token
    } else {
      // New subscriber
      const { data, error } = await supabase
        .from('email_subscribers')
        .insert({
          email,
          name,
          city_fips: RICHMOND_FIPS,
          source: 'website',
        })
        .select('unsubscribe_token')
        .single()

      if (error) {
        // Handle unique constraint violation (race condition)
        if (error.code === '23505') {
          return NextResponse.json(
            { success: true, message: 'You\'re already subscribed!', already_subscribed: true } satisfies SubscribeResponse,
            { status: 200 },
          )
        }
        console.error('Subscribe insert error:', error)
        return NextResponse.json(
          { success: false, message: 'Something went wrong. Please try again.' } satisfies SubscribeResponse,
          { status: 500 },
        )
      }
      unsubscribeToken = data.unsubscribe_token
    }

    // Send welcome email (non-blocking — don't fail subscription on email failure)
    const unsubscribeUrl = `${BASE_URL}/api/subscribe?token=${unsubscribeToken}`
    const welcome = buildWelcomeEmail(name, unsubscribeUrl)
    sendEmail({ to: email, ...welcome }).catch((err) =>
      console.error('Welcome email failed:', err),
    )

    return NextResponse.json(
      { success: true, message: 'You\'re subscribed! Check your inbox for a welcome email.' } satisfies SubscribeResponse,
      { status: 201 },
    )
  } catch {
    return NextResponse.json(
      { success: false, message: 'Invalid request.' } satisfies SubscribeResponse,
      { status: 400 },
    )
  }
}

// ─── GET: One-click unsubscribe ─────────────────────────────

export async function GET(request: NextRequest) {
  const token = request.nextUrl.searchParams.get('token')

  if (!token) {
    return NextResponse.redirect(new URL('/subscribe', BASE_URL))
  }

  try {
    const supabase = getSupabaseAdmin()

    const { data: subscriber } = await supabase
      .from('email_subscribers')
      .select('id, status')
      .eq('unsubscribe_token', token)
      .single() as { data: Pick<EmailSubscriber, 'id' | 'status'> | null; error: unknown }

    if (!subscriber) {
      return new NextResponse(unsubscribePage('Link not found', 'This unsubscribe link is invalid or has expired.'), {
        status: 404,
        headers: { 'Content-Type': 'text/html' },
      })
    }

    if (subscriber.status === 'unsubscribed') {
      return new NextResponse(unsubscribePage('Already unsubscribed', 'You\'ve already been unsubscribed from Richmond Commons updates.'), {
        status: 200,
        headers: { 'Content-Type': 'text/html' },
      })
    }

    const { error } = await supabase
      .from('email_subscribers')
      .update({
        status: 'unsubscribed',
        unsubscribed_at: new Date().toISOString(),
      })
      .eq('id', subscriber.id)

    if (error) {
      console.error('Unsubscribe error:', error)
      return new NextResponse(unsubscribePage('Error', 'Something went wrong. Please try again.'), {
        status: 500,
        headers: { 'Content-Type': 'text/html' },
      })
    }

    return new NextResponse(unsubscribePage('Unsubscribed', 'You\'ve been unsubscribed from Richmond Commons updates. You can resubscribe anytime.'), {
      status: 200,
      headers: { 'Content-Type': 'text/html' },
    })
  } catch {
    return new NextResponse(unsubscribePage('Error', 'Something went wrong. Please try again.'), {
      status: 500,
      headers: { 'Content-Type': 'text/html' },
    })
  }
}

/** Simple HTML page for unsubscribe confirmation (no React rendering needed). */
function unsubscribePage(title: string, message: string): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>${title} — Richmond Commons</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; background: #f8fafc; color: #475569; }
    .card { max-width: 440px; padding: 40px; text-align: center; }
    h1 { color: #1e3a5f; font-size: 20px; margin-bottom: 12px; }
    p { font-size: 15px; line-height: 1.6; }
    a { color: #2d5a8e; }
  </style>
</head>
<body>
  <div class="card">
    <h1>${title}</h1>
    <p>${message}</p>
    <p style="margin-top: 24px;"><a href="https://richmondcommons.org">Back to Richmond Commons</a></p>
  </div>
</body>
</html>`
}
