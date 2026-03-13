import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import type { FeedbackSubmission, FeedbackResponse, FeedbackType, FlagVerdict } from '@/lib/types'

const RICHMOND_FIPS = '0660620'

// ─── Rate Limiting ──────────────────────────────────────────

const ipRequests = new Map<string, number[]>()
const sessionRequests = new Map<string, number>()

const IP_LIMIT = 5
const SESSION_LIMIT = 10
const IP_WINDOW_MS = 60 * 60 * 1000 // 1 hour

function checkRateLimit(ip: string, sessionId: string | null): string | null {
  const now = Date.now()

  // IP rate limit: max 5 per hour
  const ipTimes = ipRequests.get(ip) ?? []
  const recentIpTimes = ipTimes.filter((t) => now - t < IP_WINDOW_MS)
  if (recentIpTimes.length >= IP_LIMIT) {
    return 'Rate limit exceeded. Please try again later.'
  }
  recentIpTimes.push(now)
  ipRequests.set(ip, recentIpTimes)

  // Session rate limit: max 10 per session lifetime
  if (sessionId) {
    const count = sessionRequests.get(sessionId) ?? 0
    if (count >= SESSION_LIMIT) {
      return 'Session submission limit reached.'
    }
    sessionRequests.set(sessionId, count + 1)
  }

  return null
}

// ─── Validation ─────────────────────────────────────────────

const VALID_FEEDBACK_TYPES: FeedbackType[] = [
  'flag_accuracy', 'data_correction', 'tip', 'missing_conflict', 'general',
]

const VALID_VERDICTS: FlagVerdict[] = ['confirm', 'dispute', 'add_context']

function validateSubmission(body: FeedbackSubmission): string | null {
  if (!body.feedback_type || !VALID_FEEDBACK_TYPES.includes(body.feedback_type)) {
    return 'Invalid feedback_type.'
  }

  if (body.feedback_type === 'flag_accuracy') {
    if (!body.entity_id) return 'entity_id is required for flag accuracy feedback.'
    if (!body.flag_verdict || !VALID_VERDICTS.includes(body.flag_verdict)) {
      return 'Valid flag_verdict is required.'
    }
    if (body.flag_verdict !== 'confirm' && (!body.description || body.description.length < 10)) {
      return 'Please provide at least 10 characters of explanation.'
    }
  }

  if (body.feedback_type === 'data_correction') {
    if (!body.field_name) return 'field_name is required for corrections.'
    if (!body.suggested_value) return 'suggested_value is required for corrections.'
  }

  if (
    (body.feedback_type === 'tip' || body.feedback_type === 'general') &&
    (!body.description || body.description.length < 10)
  ) {
    return 'Please provide at least 10 characters.'
  }

  if (body.feedback_type === 'missing_conflict') {
    if (!body.description || body.description.length < 10) {
      return 'Please provide at least 10 characters describing the conflict.'
    }
  }

  if (body.description && body.description.length > 5000) {
    return 'Description must be under 5,000 characters.'
  }

  if (body.submitter_email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(body.submitter_email)) {
    return 'Invalid email format.'
  }

  return null
}

// ─── Handler ────────────────────────────────────────────────

export async function POST(request: NextRequest) {
  try {
    const ip =
      request.headers.get('x-forwarded-for')?.split(',')[0]?.trim() ??
      request.headers.get('x-real-ip') ??
      'unknown'

    const sessionId = request.cookies.get('rtp_session')?.value ?? null

    const rateLimitError = checkRateLimit(ip, sessionId)
    if (rateLimitError) {
      return NextResponse.json(
        { success: false, reference_id: null, error: rateLimitError } satisfies FeedbackResponse,
        { status: 429 },
      )
    }

    const body = (await request.json()) as FeedbackSubmission

    const validationError = validateSubmission(body)
    if (validationError) {
      return NextResponse.json(
        { success: false, reference_id: null, error: validationError } satisfies FeedbackResponse,
        { status: 400 },
      )
    }

    const { data, error } = await supabase
      .from('user_feedback')
      .insert({
        city_fips: body.city_fips ?? RICHMOND_FIPS,
        feedback_type: body.feedback_type,
        entity_type: body.entity_type ?? null,
        entity_id: body.entity_id ?? null,
        flag_verdict: body.flag_verdict ?? null,
        field_name: body.field_name ?? null,
        current_value: body.current_value ?? null,
        suggested_value: body.suggested_value ?? null,
        conflict_nature: body.conflict_nature ?? null,
        official_name: body.official_name ?? null,
        description: body.description ?? null,
        evidence_url: body.evidence_url ?? null,
        evidence_text: body.evidence_text ?? null,
        submitter_email: body.submitter_email ?? null,
        submitter_name: body.submitter_name ?? null,
        page_url: body.page_url ?? null,
        is_anonymous: true,
        session_id: sessionId,
        status: 'pending',
      })
      .select('id')
      .single()

    if (error) {
      console.error('Feedback insert error:', error)
      return NextResponse.json(
        { success: false, reference_id: null, error: 'Failed to save feedback.' } satisfies FeedbackResponse,
        { status: 500 },
      )
    }

    const referenceId = data.id.slice(0, 8)

    const response = NextResponse.json(
      { success: true, reference_id: referenceId } satisfies FeedbackResponse,
      { status: 201 },
    )

    // Set session cookie if not present (for rate limiting across requests)
    if (!sessionId) {
      response.cookies.set('rtp_session', crypto.randomUUID(), {
        httpOnly: true,
        secure: true,
        sameSite: 'lax',
        maxAge: 60 * 60 * 24, // 24 hours
        path: '/',
      })
    }

    return response
  } catch {
    return NextResponse.json(
      { success: false, reference_id: null, error: 'Invalid request.' } satisfies FeedbackResponse,
      { status: 400 },
    )
  }
}
