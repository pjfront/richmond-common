import { NextRequest, NextResponse } from 'next/server'
import { searchHybrid, searchSite } from '@/lib/queries'
import { supabase } from '@/lib/supabase'
import { getSupabaseAdmin } from '@/lib/supabase-admin'
import { clientKey, enforceRateLimit } from '@/lib/rate-limit'
import type { SearchResultType, SearchResponse } from '@/lib/types'

// Rate authorization is Postgres-backed via web/src/lib/rate-limit.ts.

// ─── Query Embedding (OpenAI) ──────────────────────────────

const EMBEDDING_MODEL = 'text-embedding-3-small'
const EMBEDDING_DIMENSIONS = 1536
const EMBEDDING_USD_PER_MILLION_TOKENS = 0.02
const DEFAULT_MONTHLY_CAP_USD = 5
const EMBEDDING_CACHE_MAX = 128
const BUDGET_LOCK_TRUTHY = new Set(['1', 'true', 'yes', 'on'])

// Process-local optimization only. The Postgres limiter and global kill switch
// always run first; cache hits make no paid call and need no new reservation.
const embeddingCache = new Map<string, number[]>()

type ReservationRow = {
  reserved: boolean
  committed_cost: number
  reason: string
}

type OpenAIEmbeddingResponse = {
  data?: Array<{ embedding?: unknown }>
  usage?: { total_tokens?: unknown }
}

function normalizedQueryKey(text: string): string {
  return text.normalize('NFKC').trim().replace(/\s+/g, ' ').toLocaleLowerCase('en-US')
}

function getCachedEmbedding(text: string): number[] | null {
  const key = normalizedQueryKey(text)
  const cached = embeddingCache.get(key)
  if (!cached) return null
  embeddingCache.delete(key)
  embeddingCache.set(key, cached)
  return cached
}

function cacheEmbedding(text: string, embedding: number[]): void {
  const key = normalizedQueryKey(text)
  embeddingCache.delete(key)
  embeddingCache.set(key, embedding)
  while (embeddingCache.size > EMBEDDING_CACHE_MAX) {
    const oldest = embeddingCache.keys().next().value as string | undefined
    if (oldest === undefined) break
    embeddingCache.delete(oldest)
  }
}

function monthlyCapUsd(): number | null {
  const raw = process.env.RICHMOND_API_MONTHLY_CAP_USD
  if (!raw) return DEFAULT_MONTHLY_CAP_USD
  const parsed = Number(raw)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null
}

function embeddingCost(tokens: number): number {
  return tokens / 1_000_000 * EMBEDDING_USD_PER_MILLION_TOKENS
}

function budgetLocked(): boolean {
  return BUDGET_LOCK_TRUTHY.has(
    (process.env.RICHMOND_API_BUDGET_LOCK ?? '').trim().toLowerCase(),
  )
}

async function embedQuery(text: string): Promise<number[] | null> {
  // The global kill switch is an authorization boundary, so it precedes even
  // the free process-local cache. Locked requests use keyword search only.
  if (budgetLocked()) return null

  const cached = getCachedEmbedding(text)
  if (cached) return cached

  const openaiKey = process.env.OPENAI_API_KEY
  const monthlyCap = monthlyCapUsd()
  if (!openaiKey || monthlyCap === null) return null

  // UTF-8 bytes conservatively upper-bound embedding tokens: each tokenizer
  // token consumes at least one byte. The reservation happens before fetch.
  const projectedTokens = new TextEncoder().encode(text).length
  const projectedCost = embeddingCost(projectedTokens)
  const reservationId = crypto.randomUUID()

  try {
    const admin = getSupabaseAdmin()
    const { data: reservationData, error: reservationError } = await admin.rpc(
      'reserve_llm_cost',
      {
        p_reservation_id: reservationId,
        p_city_fips: '0660620',
        p_model: EMBEDDING_MODEL,
        p_caller: 'web_search',
        p_projected_cost: projectedCost,
        p_monthly_cap: monthlyCap,
        p_event_type: 'search_embedding',
        p_metadata: { provider: 'openai', endpoint: '/v1/embeddings' },
      },
    )
    const reservation = (
      Array.isArray(reservationData) ? reservationData[0] : reservationData
    ) as ReservationRow | null
    if (reservationError || !reservation?.reserved) {
      if (reservationError) {
        console.error('Embedding reservation failed:', reservationError.message)
      }
      return null
    }

    // Native fetch performs one request; there is no SDK retry layer here.
    const response = await fetch('https://api.openai.com/v1/embeddings', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${openaiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: EMBEDDING_MODEL,
        input: text,
        dimensions: EMBEDDING_DIMENSIONS,
      }),
    })

    if (!response.ok) {
      console.error('OpenAI embedding error:', response.status)
      return null
    }

    const payload = await response.json() as OpenAIEmbeddingResponse
    const totalTokens = payload.usage?.total_tokens
    if (
      !Number.isSafeInteger(totalTokens)
      || (totalTokens as number) <= 0
    ) {
      console.error('OpenAI embedding response omitted valid usage')
      return null
    }

    const actualCost = embeddingCost(totalTokens as number)
    const { data: settled, error: settlementError } = await admin.rpc(
      'settle_llm_cost_reservation',
      {
        p_reservation_id: reservationId,
        p_actual_cost: actualCost,
        p_input_tokens: totalTokens as number,
        p_output_tokens: 0,
        p_metadata: {
          provider: 'openai',
          endpoint: '/v1/embeddings',
          price_per_million_tokens: EMBEDDING_USD_PER_MILLION_TOKENS,
        },
      },
    )
    if (settlementError || settled !== true) {
      console.error(
        'Embedding settlement failed:',
        settlementError?.message ?? 'reservation was not open',
      )
      return null
    }

    // The paid call is durably accounted for before its vector is trusted.
    // A malformed vector can fall back safely without losing the cost record.
    const embedding = payload.data?.[0]?.embedding
    if (
      !Array.isArray(embedding)
      || embedding.length !== EMBEDDING_DIMENSIONS
      || !embedding.every((value) => typeof value === 'number' && Number.isFinite(value))
    ) {
      console.error('OpenAI embedding response omitted a valid vector')
      return null
    }

    const vector = embedding as number[]
    cacheEmbedding(text, vector)
    return vector
  } catch (err) {
    console.error('Embedding request/accounting failed:', err)
    return null
  }
}

// ─── Analytics Logging ─────────────────────────────────────

async function logSearchQuery(
  query: string,
  resultCount: number,
  searchMode: string,
  typeFilter: string | null,
  clientIp: string,
): Promise<void> {
  try {
    // SHA-256 hash of IP — no PII stored
    const encoder = new TextEncoder()
    const data = encoder.encode(clientIp)
    const hashBuffer = await crypto.subtle.digest('SHA-256', data)
    const hashArray = Array.from(new Uint8Array(hashBuffer))
    const clientHash = hashArray.map((b) => b.toString(16).padStart(2, '0')).join('')

    // Fire-and-forget — don't await, don't block the response
    supabase.from('search_queries').insert({
      query_text: query,
      result_count: resultCount,
      search_mode: searchMode,
      result_type_filter: typeFilter,
      client_hash: clientHash,
    }).then(({ error }) => {
      if (error) console.error('Search analytics log error:', error)
    })
  } catch {
    // Analytics failure should never break search
  }
}

// ─── Validation ─────────────────────────────────────────────

const VALID_TYPES: SearchResultType[] = ['agenda_item', 'official', 'vote_explainer', 'meeting']
const MAX_LIMIT = 50
const DEFAULT_LIMIT = 20

// ─── GET /api/search ────────────────────────────────────────

export async function GET(request: NextRequest) {
  const ip = clientKey(request, 'unknown')
  const rateLimit = await enforceRateLimit('search', ip)
  if (!rateLimit.allowed && rateLimit.response) {
    // enforceRateLimit only creates a 429 after the atomic counter proves the
    // per-IP limit was exceeded. Backend failures remain allowed-but-untrusted.
    return rateLimit.response
  }

  const { searchParams } = request.nextUrl
  const q = searchParams.get('q')?.trim() ?? ''
  const type = searchParams.get('type') as SearchResultType | null
  const limitParam = parseInt(searchParams.get('limit') ?? String(DEFAULT_LIMIT), 10)
  const offsetParam = parseInt(searchParams.get('offset') ?? '0', 10)

  // Validate query
  if (!q || q.length < 2) {
    return NextResponse.json(
      { error: 'Query must be at least 2 characters.' },
      { status: 400 }
    )
  }
  if (q.length > 200) {
    return NextResponse.json(
      { error: 'Query must be 200 characters or fewer.' },
      { status: 400 }
    )
  }

  // Validate type filter
  if (type && !VALID_TYPES.includes(type)) {
    return NextResponse.json(
      { error: `Invalid type. Must be one of: ${VALID_TYPES.join(', ')}` },
      { status: 400 }
    )
  }

  // Clamp limit/offset
  const limit = Math.min(Math.max(1, isNaN(limitParam) ? DEFAULT_LIMIT : limitParam), MAX_LIMIT)
  const offset = Math.max(0, isNaN(offsetParam) ? 0 : offsetParam)

  try {
    // A limiter backend failure may still serve free keyword search, but it
    // cannot authorize paid work. Reservation/settlement failures inside
    // embedQuery follow the same keyword-only fallback.
    const queryEmbedding = (
      rateLimit.allowed && rateLimit.backendAvailable
        ? await embedQuery(q)
        : null
    )
    const searchMode = queryEmbedding ? 'hybrid' : 'keyword'

    let results
    if (queryEmbedding) {
      results = await searchHybrid(q, queryEmbedding, {
        resultType: type ?? undefined,
        limit,
        offset,
      })
    } else {
      // Fallback to pure FTS when no embedding available
      const ftsResults = await searchSite(q, {
        resultType: type ?? undefined,
        limit,
        offset,
      })
      // Add match_type to FTS-only results for type compatibility
      results = ftsResults.map((r) => ({ ...r, match_type: 'keyword' as const }))
    }

    // Log analytics (fire-and-forget)
    logSearchQuery(q, results.length, searchMode, type, ip)

    const response: SearchResponse = {
      results,
      query: q,
      limit,
      offset,
    }

    return NextResponse.json(response, {
      headers: {
        'Cache-Control': 'public, s-maxage=300',
      },
    })
  } catch (err) {
    console.error('Search API error:', err)
    return NextResponse.json(
      { error: 'Search failed. Please try again.' },
      { status: 500 }
    )
  }
}
