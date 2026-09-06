import { NextResponse, type NextRequest } from 'next/server'
import { getSupabaseAdmin } from '@/lib/supabase-admin'
import { withOperatorAuth } from '@/lib/operator-auth'
import { REVIEW_ACTIONS, type ReviewAction, type ReviewDecision } from '@/lib/decision-review'
import type {
  DecisionSeverity,
  DecisionQueueResponse,
} from '@/lib/types'

const RICHMOND_FIPS = '0660620'

// Severity ranking for ordering (matches Python CASE expression)
const SEVERITY_RANK: Record<DecisionSeverity, number> = {
  critical: 1,
  high: 2,
  medium: 3,
  low: 4,
  info: 5,
}

export const GET = withOperatorAuth(async () => {
  try {
    // Instantiate privileged access only after withOperatorAuth validates the session.
    const supabase = getSupabaseAdmin()
    // Run pending and resolved queries in parallel
    const [pendingResult, resolvedResult] = await Promise.all([
      supabase
        .from('pending_decisions')
        .select('*, candidate:civic_brief_candidates!target_brief_id(id,kind,subject_key,title,body,sources,content_version,status,input_fingerprint,published_at)')
        .eq('city_fips', RICHMOND_FIPS)
        .in('status', ['pending', 'deferred'])
        .order('created_at', { ascending: true })
        .limit(100),

      supabase
        .from('pending_decisions')
        .select('*, candidate:civic_brief_candidates!target_brief_id(id,kind,subject_key,title,body,sources,content_version,status,input_fingerprint,published_at)')
        .eq('city_fips', RICHMOND_FIPS)
        .in('status', ['approved', 'rejected', 'resolved'])
        .order('resolved_at', { ascending: false })
        .limit(20),
    ])

    if (pendingResult.error) throw pendingResult.error
    if (resolvedResult.error) throw resolvedResult.error

    const active = (pendingResult.data ?? []) as ReviewDecision[]
    const pending = active.filter(decision => decision.status === 'pending')
    const deferred = active.filter(decision => decision.status === 'deferred')
    const resolved = (resolvedResult.data ?? []) as ReviewDecision[]
    const ids = [...active, ...resolved].map(decision => decision.id)
    const historyResult = ids.length
      ? await supabase.from('operator_decision_events')
        .select('id,decision_id,action,actor,note,expected_version,created_at')
        .in('decision_id', ids).order('created_at', { ascending: false }).limit(200)
      : { data: [], error: null }
    if (historyResult.error) throw historyResult.error

    // Sort pending by severity rank then age (oldest first within rank)
    pending.sort((a, b) => {
      const rankA = SEVERITY_RANK[a.severity] ?? 5
      const rankB = SEVERITY_RANK[b.severity] ?? 5
      if (rankA !== rankB) return rankA - rankB
      return new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
    })

    // Count by severity
    const counts: Record<DecisionSeverity, number> = {
      critical: 0,
      high: 0,
      medium: 0,
      low: 0,
      info: 0,
    }
    for (const d of pending) {
      if (d.severity in counts) {
        counts[d.severity]++
      }
    }

    const response: DecisionQueueResponse & { deferred: ReviewDecision[]; history: unknown[]; limited: boolean } = {
      summary: {
        total_pending: pending.length,
        counts,
      },
      pending,
      deferred,
      recently_resolved: resolved,
      history: historyResult.data ?? [],
      limited: active.length === 100,
    }

    // No caching — operator data should always be fresh
    return NextResponse.json(response, { headers: { 'Cache-Control': 'private, no-store' } })
  } catch (err) {
    console.error('Decision queue fetch failed:', err)
    return NextResponse.json(
      { error: 'Failed to fetch decision queue' },
      { status: 500 },
    )
  }
})

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

export const POST = withOperatorAuth(async (request: NextRequest) => {
  // Cookies authorize the operator; a required same-origin JSON request
  // prevents a third-party page from spending that authority through CSRF.
  const origin = request.headers.get('origin')
  const site = request.headers.get('sec-fetch-site')
  if (origin !== new URL(request.url).origin || (site && site !== 'same-origin')) {
    return NextResponse.json({ error: 'Same-origin review request required' }, { status: 403 })
  }
  if (request.headers.get('content-type')?.split(';')[0].trim() !== 'application/json') {
    return NextResponse.json({ error: 'JSON request required' }, { status: 415 })
  }
  if (Number(request.headers.get('content-length') ?? 0) > 20_000) {
    return NextResponse.json({ error: 'Request too large' }, { status: 413 })
  }
  let body: Record<string, unknown>
  try {
    const text = await request.text()
    if (text.length > 20_000) return NextResponse.json({ error: 'Request too large' }, { status: 413 })
    const parsed: unknown = JSON.parse(text)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('Invalid object')
    body = parsed as Record<string, unknown>
  } catch {
    return NextResponse.json({ error: 'Invalid JSON request' }, { status: 400 })
  }
  if (Object.keys(body).some(key => !['decision_id', 'action', 'expected_version', 'idempotency_key', 'note'].includes(key))
      || typeof body.decision_id !== 'string' || !UUID.test(body.decision_id)
      || typeof body.idempotency_key !== 'string' || !UUID.test(body.idempotency_key)
      || typeof body.action !== 'string' || !REVIEW_ACTIONS.includes(body.action as ReviewAction)
      || !Number.isSafeInteger(body.expected_version) || Number(body.expected_version) < 1
      || (body.note !== undefined && body.note !== null && (typeof body.note !== 'string' || body.note.length > 4000))) {
    return NextResponse.json({ error: 'Invalid review request' }, { status: 400 })
  }
  try {
    const { data, error } = await getSupabaseAdmin().rpc('review_decision', {
      p_decision_id: body.decision_id,
      p_action: body.action,
      p_expected_version: body.expected_version,
      p_idempotency_key: body.idempotency_key,
      p_note: body.note ?? null,
      p_actor: 'operator',
    })
    if (error) {
      const code = error.code === '23505' ? 'duplicate_open_decision' : 'review_failed'
      return NextResponse.json({ ok: false, code }, { status: error.code === '23505' ? 409 : 500 })
    }
    if (!data || typeof data.ok !== 'boolean') throw new Error('Invalid review response')
    const status = data.ok ? 200 : data.code === 'not_found' ? 404 : 409
    return NextResponse.json(data, { status, headers: { 'Cache-Control': 'private, no-store' } })
  } catch {
    return NextResponse.json({ ok: false, code: 'review_failed' }, { status: 500 })
  }
})
