import { NextRequest, NextResponse } from 'next/server'
import { randomUUID } from 'node:crypto'
import { getSupabaseAdmin } from '@/lib/supabase-admin'
import { buildWelcomeEmail, buildOrientationEmail } from '@/lib/email'
import {
  deliverTrackedEmail,
  welcomeContentKey,
  type DeliveryResult,
} from '@/lib/email-delivery'
import { clientKey, enforceRateLimit } from '@/lib/rate-limit'
import { emailHash, logEvent, requestContext } from '@/lib/logger'
import type { SubscribeResponse, EmailSubscriber, Provenance } from '@/lib/types'
import type { SupabaseClient } from '@supabase/supabase-js'

const RICHMOND_FIPS = '0660620'
const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://richmondcommons.org'
const ACQUISITION_SURFACES = new Set([
  'homepage',
  'nav',
  'footer',
  'meeting',
  'subscribe_page',
  'november_election',
])
const SUBSCRIBE_SUCCESS = {
  success: true,
  message: 'If this address can receive Richmond Commons updates, check the inbox for next steps.',
} satisfies SubscribeResponse

function subscribeSuccessResponse() {
  return NextResponse.json(SUBSCRIBE_SUCCESS, { status: 202 })
}

/**
 * Send the next upcoming regular meeting's orientation preview to a new
 * subscriber. The tracked attempt is awaited so a serverless response cannot
 * strand it; failures are logged but never roll back a valid subscription.
 *
 * Records last_orientation_meeting_id so the daily broadcast skips this
 * subscriber for the same meeting and avoids a duplicate email.
 */
async function sendNextOrientationToSubscriber(
  supabase: SupabaseClient,
  subscriberId: string,
  email: string,
  unsubscribeToken: string,
): Promise<DeliveryResult | null> {
  try {
    const today = new Date().toISOString().split('T')[0]
    const { data: meeting } = await supabase
      .from('meetings')
      .select('id, meeting_date, orientation_preview, orientation_preview_provenance, agenda_url')
      .eq('city_fips', RICHMOND_FIPS)
      .eq('meeting_type', 'regular')
      .gte('meeting_date', today)
      .is('source_cancelled_at', null)
      .not('orientation_preview', 'is', null)
      .order('meeting_date', { ascending: true })
      .limit(1)
      .maybeSingle()

    if (!meeting?.orientation_preview) return null

    const result = await deliverTrackedEmail({
      supabase,
      subscriber: { id: subscriberId, email, unsubscribe_token: unsubscribeToken },
      kind: 'orientation',
      contentKey: `meeting:${meeting.id as string}`,
      build: ({ unsubscribeUrl, manageUrl }) => buildOrientationEmail(
        {
          id: meeting.id as string,
          meeting_date: meeting.meeting_date as string,
          orientation_preview: meeting.orientation_preview as string,
          orientation_preview_provenance: (meeting.orientation_preview_provenance ?? null) as Provenance | null,
          agenda_url: meeting.agenda_url as string | null,
        },
        unsubscribeUrl,
        manageUrl,
      ),
    })
    if (result.status === 'sent') {
      await supabase
        .from('email_subscribers')
        .update({ last_orientation_meeting_id: meeting.id as string })
        .eq('id', subscriberId)
    }
    return result
  } catch (err) {
    console.error('Signup-time orientation send failed:', err)
    return {
      subscriberId,
      status: 'failed',
      error: 'Signup-time orientation delivery failed',
    }
  }
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
  const ctx = requestContext(request)
  try {
    const limit = await enforceRateLimit('subscribe', clientKey(request, 'unknown'))
    if (!limit.allowed) {
      logEvent('subscribe.rate_limited', { ...ctx, severity: 'warn' })
      return limit.response!
    }

    const body = await request.json() as Record<string, unknown>
    const email = (typeof body.email === 'string' ? body.email : '').toLowerCase().trim()
    const name = typeof body.name === 'string' ? body.name.trim().slice(0, 200) || null : null
    const requestedSurface = typeof body.surface === 'string' ? body.surface : 'subscribe_page'
    const acquisitionSurface = ACQUISITION_SURFACES.has(requestedSurface)
      ? requestedSurface
      : 'subscribe_page'

    const emailError = validateEmail(email)
    if (emailError) {
      logEvent('subscribe.invalid_email', { ...ctx, severity: 'warn' })
      return NextResponse.json(
        { success: false, message: emailError } satisfies SubscribeResponse,
        { status: 400 },
      )
    }
    const emailH = await emailHash(email)

    const supabase = getSupabaseAdmin()

    // Check if already exists
    const { data: existing } = await supabase
      .from('email_subscribers')
      .select('id, name, status, subscribed_at, unsubscribe_token')
      .eq('email', email)
      .single() as { data: Pick<EmailSubscriber, 'id' | 'name' | 'status' | 'subscribed_at' | 'unsubscribe_token'> | null; error: unknown }

    if (existing && existing.status === 'active') {
      logEvent('subscribe.already_active', { ...ctx, email_hash: emailH })
      return subscribeSuccessResponse()
    }

    let unsubscribeToken: string
    let subscriberId: string
    let subscriberName = name
    // No database default is allowed for this marker: only this new route may
    // opt a real new/reactivated subscription into activation history and its
    // atomically paired welcome intent.
    const activationId = randomUUID()
    const activationAt = new Date().toISOString()

    if (existing) {
      // Re-subscribe: was previously unsubscribed
      const rotatedUnsubscribeToken = randomUUID()
      const { data: reactivated, error } = await supabase
        .from('email_subscribers')
        .update({
          status: 'active',
          name: name ?? existing.name, // keep existing name if not provided
          subscribed_at: activationAt,
          unsubscribed_at: null,
          // A reactivation is a new authorization cycle. Invalidating the old
          // bearer token prevents links from the prior cycle managing it.
          unsubscribe_token: rotatedUnsubscribeToken,
          current_activation_id: activationId,
          current_activation_at: activationAt,
          current_activation_surface: acquisitionSurface,
        })
        .eq('id', existing.id)
        .eq('status', 'unsubscribed')
        .select('id, unsubscribe_token')
        .maybeSingle()

      if (error) {
        logEvent('subscribe.resubscribe_error', {
          ...ctx,
          severity: 'error',
          email_hash: emailH,
          message: error.message,
        })
        return NextResponse.json(
          { success: false, message: 'Something went wrong. Please try again.' } satisfies SubscribeResponse,
          { status: 500 },
        )
      }
      if (!reactivated) {
        logEvent('subscribe.resubscribe_race', { ...ctx, email_hash: emailH })
        return subscribeSuccessResponse()
      }
      logEvent('subscribe.resubscribed', { ...ctx, email_hash: emailH })
      unsubscribeToken = reactivated.unsubscribe_token
      subscriberId = existing.id
      subscriberName = name ?? existing.name
    } else {
      // New subscriber
      const { data, error } = await supabase
        .from('email_subscribers')
        .insert({
          email,
          name,
          city_fips: RICHMOND_FIPS,
          source: 'website',
          subscribed_at: activationAt,
          current_activation_id: activationId,
          current_activation_at: activationAt,
          current_activation_surface: acquisitionSurface,
        })
        .select('id, unsubscribe_token')
        .single()

      if (error) {
        // Handle unique constraint violation (race condition)
        if (error.code === '23505') {
          logEvent('subscribe.race_collision', { ...ctx, email_hash: emailH })
          return subscribeSuccessResponse()
        }
        logEvent('subscribe.insert_error', {
          ...ctx,
          severity: 'error',
          email_hash: emailH,
          message: error.message,
        })
        return NextResponse.json(
          { success: false, message: 'Something went wrong. Please try again.' } satisfies SubscribeResponse,
          { status: 500 },
        )
      }
      logEvent('subscribe.created', { ...ctx, email_hash: emailH })
      unsubscribeToken = data.unsubscribe_token
      subscriberId = data.id
    }

    // Claim and attempt the welcome delivery before returning. Provider failures
    // are durable and retryable, but do not roll back a successful subscription.
    let welcomeResult: DeliveryResult
    try {
      welcomeResult = await deliverTrackedEmail({
        supabase,
        subscriber: { id: subscriberId, email, unsubscribe_token: unsubscribeToken },
        kind: 'welcome',
        // The trigger already inserted this exact pending intent in the same
        // transaction as the activation. Retries reuse the activation UUID.
        contentKey: welcomeContentKey(activationId),
        build: ({ unsubscribeUrl, manageUrl }) =>
          buildWelcomeEmail(subscriberName, unsubscribeUrl, manageUrl),
      })
    } catch (error) {
      // The subscription write already succeeded. Preserve that truth even if
      // an unexpected transport/client exception escapes the delivery helper.
      console.error('Welcome delivery attempt failed:', error)
      welcomeResult = {
        subscriberId,
        status: 'failed',
        error: 'Welcome delivery attempt failed',
      }
    }
    if (welcomeResult.status === 'failed' || welcomeResult.status === 'manual_review') {
      logEvent('subscribe.welcome_failed', {
        ...ctx,
        severity: 'error',
        email_hash: emailH,
        message: welcomeResult.error,
      })
    }

    // Claim and attempt the next meeting preview, if one is ready. Awaiting the
    // tracked attempt prevents a serverless response from stranding the send.
    await sendNextOrientationToSubscriber(
      supabase,
      subscriberId,
      email,
      unsubscribeToken,
    )

    // Delivery disposition is intentionally confined to structured logs and
    // operator views. A public response must not reveal address membership.
    return subscribeSuccessResponse()
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
        headers: { 'Content-Type': 'text/html', 'Referrer-Policy': 'no-referrer' },
      })
    }

    if (subscriber.status === 'unsubscribed') {
      return new NextResponse(unsubscribePage('Already unsubscribed', 'You\'ve already been unsubscribed from Richmond Commons updates.'), {
        status: 200,
        headers: { 'Content-Type': 'text/html', 'Referrer-Policy': 'no-referrer' },
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
        headers: { 'Content-Type': 'text/html', 'Referrer-Policy': 'no-referrer' },
      })
    }

    return new NextResponse(unsubscribePage('Unsubscribed', 'You\'ve been unsubscribed from Richmond Commons updates. You can resubscribe anytime.'), {
      status: 200,
      headers: { 'Content-Type': 'text/html', 'Referrer-Policy': 'no-referrer' },
    })
  } catch {
    return new NextResponse(unsubscribePage('Error', 'Something went wrong. Please try again.'), {
      status: 500,
      headers: { 'Content-Type': 'text/html', 'Referrer-Policy': 'no-referrer' },
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
  <meta name="referrer" content="no-referrer"/>
  <title>${title} | Richmond Commons</title>
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
