import { NextRequest, NextResponse } from 'next/server'
import { getSupabaseAdmin } from '@/lib/supabase-admin'
import { RICHMOND_LOCAL_ISSUES } from '@/lib/local-issues'
import type {
  EmailSubscriber,
  EmailPreference,
  SubscriptionPreferences,
  PreferencesResponse,
} from '@/lib/types'

const RICHMOND_FIPS = '0660620'
const VALID_TOPIC_IDS = new Set(RICHMOND_LOCAL_ISSUES.map((i) => i.id))
const VALID_DISTRICTS = new Set(['1', '2', '3', '4', '5', '6'])

// ─── Rate Limiting ──────────────────────────────────────────

const tokenRequests = new Map<string, number[]>()
const TOKEN_LIMIT = 10
const TOKEN_WINDOW_MS = 60 * 60 * 1000 // 1 hour

function checkRateLimit(token: string): string | null {
  const now = Date.now()
  const times = tokenRequests.get(token) ?? []
  const recent = times.filter((t) => now - t < TOKEN_WINDOW_MS)
  if (recent.length >= TOKEN_LIMIT) {
    return 'Too many requests. Please try again later.'
  }
  recent.push(now)
  tokenRequests.set(token, recent)
  return null
}

// ─── Auth ───────────────────────────────────────────────────

async function authenticateSubscriber(token: string | null) {
  if (!token) return { subscriber: null, error: 'Missing token.' }

  const supabase = getSupabaseAdmin()
  const { data } = await supabase
    .from('email_subscribers')
    .select('id, name, status')
    .eq('unsubscribe_token', token)
    .single() as { data: Pick<EmailSubscriber, 'id' | 'name' | 'status'> | null; error: unknown }

  if (!data) return { subscriber: null, error: 'Invalid or expired link.' }
  if (data.status === 'unsubscribed') return { subscriber: null, error: 'This subscription is no longer active.' }

  return { subscriber: data, error: null }
}

// ─── Helpers ────────────────────────────────────────────────

function groupPreferences(rows: EmailPreference[]): SubscriptionPreferences {
  const prefs: SubscriptionPreferences = { topics: [], districts: [], candidates: [] }
  for (const row of rows) {
    if (row.preference_type === 'topic') prefs.topics.push(row.preference_value)
    else if (row.preference_type === 'district') prefs.districts.push(row.preference_value)
    else if (row.preference_type === 'candidate') prefs.candidates.push(row.preference_value)
  }
  return prefs
}

// ─── GET: Load preferences ──────────────────────────────────

export async function GET(request: NextRequest) {
  const token = request.nextUrl.searchParams.get('token')
  const { subscriber, error } = await authenticateSubscriber(token)

  if (!subscriber) {
    return NextResponse.json(
      { success: false, error } satisfies PreferencesResponse,
      { status: token ? 403 : 400 },
    )
  }

  const supabase = getSupabaseAdmin()
  const { data: rows } = await supabase
    .from('email_preferences')
    .select('*')
    .eq('subscriber_id', subscriber.id) as { data: EmailPreference[] | null; error: unknown }

  return NextResponse.json(
    { success: true, preferences: groupPreferences(rows ?? []) } satisfies PreferencesResponse,
    { status: 200 },
  )
}

// ─── PATCH: Save preferences ────────────────────────────────

export async function PATCH(request: NextRequest) {
  try {
    const body = await request.json() as Record<string, unknown>
    const token = typeof body.token === 'string' ? body.token : null

    const rateLimitError = checkRateLimit(token ?? 'unknown')
    if (rateLimitError) {
      return NextResponse.json(
        { success: false, error: rateLimitError } satisfies PreferencesResponse,
        { status: 429 },
      )
    }

    const { subscriber, error: authError } = await authenticateSubscriber(token)
    if (!subscriber) {
      return NextResponse.json(
        { success: false, error: authError } satisfies PreferencesResponse,
        { status: 403 },
      )
    }

    const prefs = body.preferences as SubscriptionPreferences | undefined
    if (!prefs || typeof prefs !== 'object') {
      return NextResponse.json(
        { success: false, error: 'Missing preferences.' } satisfies PreferencesResponse,
        { status: 400 },
      )
    }

    // Validate + normalize
    const topics = Array.isArray(prefs.topics) ? prefs.topics.filter((t): t is string => typeof t === 'string' && VALID_TOPIC_IDS.has(t)) : []
    const districts = Array.isArray(prefs.districts) ? prefs.districts.filter((d): d is string => typeof d === 'string' && VALID_DISTRICTS.has(d)) : []
    const candidateIds = Array.isArray(prefs.candidates) ? prefs.candidates.filter((c): c is string => typeof c === 'string' && c.length > 0) : []

    // Validate candidate IDs against database
    const supabase = getSupabaseAdmin()
    let validCandidates: string[] = []
    if (candidateIds.length > 0) {
      const { data: found } = await supabase
        .from('election_candidates')
        .select('id')
        .in('id', candidateIds)
        .eq('city_fips', RICHMOND_FIPS)

      validCandidates = (found ?? []).map((c: { id: string }) => c.id)
    }

    // Build insert rows
    const rows: Array<{
      subscriber_id: string
      preference_type: string
      preference_value: string
      city_fips: string
    }> = [
      ...topics.map((v) => ({ subscriber_id: subscriber.id, preference_type: 'topic' as const, preference_value: v, city_fips: RICHMOND_FIPS })),
      ...districts.map((v) => ({ subscriber_id: subscriber.id, preference_type: 'district' as const, preference_value: v, city_fips: RICHMOND_FIPS })),
      ...validCandidates.map((v) => ({ subscriber_id: subscriber.id, preference_type: 'candidate' as const, preference_value: v, city_fips: RICHMOND_FIPS })),
    ]

    // Replace: delete all existing, insert new set
    await supabase
      .from('email_preferences')
      .delete()
      .eq('subscriber_id', subscriber.id)

    if (rows.length > 0) {
      const { error: insertError } = await supabase
        .from('email_preferences')
        .insert(rows)

      if (insertError) {
        console.error('Preferences insert error:', insertError)
        return NextResponse.json(
          { success: false, error: 'Failed to save preferences.' } satisfies PreferencesResponse,
          { status: 500 },
        )
      }
    }

    const savedPrefs: SubscriptionPreferences = {
      topics,
      districts,
      candidates: validCandidates,
    }

    return NextResponse.json(
      { success: true, preferences: savedPrefs } satisfies PreferencesResponse,
      { status: 200 },
    )
  } catch {
    return NextResponse.json(
      { success: false, error: 'Invalid request.' } satisfies PreferencesResponse,
      { status: 400 },
    )
  }
}
