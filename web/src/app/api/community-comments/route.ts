import { NextRequest, NextResponse } from 'next/server'
import { createHash } from 'crypto'
import { supabase } from '@/lib/supabase'
import type { CommunityCommentSubmission, CommunityCommentResponse } from '@/lib/types'

const RICHMOND_FIPS = '0660620'

// ─── Rate Limiting ──────────────────────────────────────────

const ipRequests = new Map<string, number[]>()
const sessionRequests = new Map<string, number>()

const IP_LIMIT = 10       // 10 comments per hour per IP
const SESSION_LIMIT = 30  // 30 comments per session lifetime
const IP_WINDOW_MS = 60 * 60 * 1000

function checkRateLimit(ip: string, sessionId: string | null): string | null {
  const now = Date.now()

  const ipTimes = ipRequests.get(ip) ?? []
  const recentIpTimes = ipTimes.filter((t) => now - t < IP_WINDOW_MS)
  if (recentIpTimes.length >= IP_LIMIT) {
    return 'Rate limit exceeded. Please try again later.'
  }
  recentIpTimes.push(now)
  ipRequests.set(ip, recentIpTimes)

  if (sessionId) {
    const count = sessionRequests.get(sessionId) ?? 0
    if (count >= SESSION_LIMIT) {
      return 'Session comment limit reached.'
    }
    sessionRequests.set(sessionId, count + 1)
  }

  return null
}

// ─── Validation ─────────────────────────────────────────────

function validateSubmission(body: CommunityCommentSubmission): string | null {
  if (!body.agenda_item_id || typeof body.agenda_item_id !== 'string') {
    return 'agenda_item_id is required.'
  }

  if (!body.author_name || typeof body.author_name !== 'string' || body.author_name.trim().length < 2) {
    return 'Name is required (at least 2 characters).'
  }

  if (body.author_name.trim().length > 200) {
    return 'Name must be under 200 characters.'
  }

  if (!body.comment_text || typeof body.comment_text !== 'string' || body.comment_text.trim().length < 5) {
    return 'Comment must be at least 5 characters.'
  }

  if (body.comment_text.length > 5000) {
    return 'Comment must be under 5,000 characters.'
  }

  if (body.author_email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(body.author_email)) {
    return 'Invalid email format.'
  }

  if (body.parent_comment_id && typeof body.parent_comment_id !== 'string') {
    return 'Invalid parent_comment_id.'
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
        { success: false, comment_id: null, error: rateLimitError } satisfies CommunityCommentResponse,
        { status: 429 },
      )
    }

    const body = (await request.json()) as CommunityCommentSubmission

    const validationError = validateSubmission(body)
    if (validationError) {
      return NextResponse.json(
        { success: false, comment_id: null, error: validationError } satisfies CommunityCommentResponse,
        { status: 400 },
      )
    }

    // Verify the agenda item exists
    const { data: itemCheck } = await supabase
      .from('agenda_items')
      .select('id, meeting_id')
      .eq('id', body.agenda_item_id)
      .eq('city_fips', RICHMOND_FIPS)
      .single()

    if (!itemCheck) {
      return NextResponse.json(
        { success: false, comment_id: null, error: 'Agenda item not found.' } satisfies CommunityCommentResponse,
        { status: 404 },
      )
    }

    // If replying, verify parent comment exists and belongs to same item
    if (body.parent_comment_id) {
      const { data: parentCheck } = await supabase
        .from('community_comments')
        .select('id')
        .eq('id', body.parent_comment_id)
        .eq('agenda_item_id', body.agenda_item_id)
        .eq('status', 'published')
        .single()

      if (!parentCheck) {
        return NextResponse.json(
          { success: false, comment_id: null, error: 'Parent comment not found.' } satisfies CommunityCommentResponse,
          { status: 404 },
        )
      }
    }

    const ipHash = createHash('sha256').update(ip + RICHMOND_FIPS).digest('hex').slice(0, 16)

    const { data, error } = await supabase
      .from('community_comments')
      .insert({
        city_fips: RICHMOND_FIPS,
        agenda_item_id: body.agenda_item_id,
        parent_comment_id: body.parent_comment_id ?? null,
        author_name: body.author_name.trim(),
        author_email: body.author_email?.trim() ?? null,
        comment_text: body.comment_text.trim(),
        status: 'published',
        ip_hash: ipHash,
        session_id: sessionId,
      })
      .select('id')
      .single()

    if (error) {
      console.error('Community comment insert error:', error)
      return NextResponse.json(
        { success: false, comment_id: null, error: 'Failed to save comment.' } satisfies CommunityCommentResponse,
        { status: 500 },
      )
    }

    const response = NextResponse.json(
      { success: true, comment_id: data.id } satisfies CommunityCommentResponse,
      { status: 201 },
    )

    // Set session cookie if not present
    if (!sessionId) {
      response.cookies.set('rtp_session', crypto.randomUUID(), {
        httpOnly: true,
        secure: true,
        sameSite: 'lax',
        maxAge: 60 * 60 * 24,
        path: '/',
      })
    }

    return response
  } catch {
    return NextResponse.json(
      { success: false, comment_id: null, error: 'Invalid request.' } satisfies CommunityCommentResponse,
      { status: 400 },
    )
  }
}
