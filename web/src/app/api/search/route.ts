import { NextRequest, NextResponse } from 'next/server'
import { searchHybrid, searchSite } from '@/lib/queries'
import { supabase } from '@/lib/supabase'
import type { SearchResultType, SearchResponse } from '@/lib/types'

// ─── Rate Limiting (in-memory, same pattern as feedback route) ───

const ipRequests = new Map<string, number[]>()
const IP_LIMIT = 15
const IP_WINDOW_MS = 60 * 1000 // 1 minute

function checkRateLimit(ip: string): boolean {
  const now = Date.now()
  const times = ipRequests.get(ip) ?? []
  const recent = times.filter((t) => now - t < IP_WINDOW_MS)
  if (recent.length >= IP_LIMIT) return false
  recent.push(now)
  ipRequests.set(ip, recent)
  return true
}

// ─── Query Embedding (OpenAI) ──────────────────────────────

let openaiKey: string | undefined

async function embedQuery(text: string): Promise<number[] | null> {
  openaiKey ??= process.env.OPENAI_API_KEY
  if (!openaiKey) return null

  try {
    const response = await fetch('https://api.openai.com/v1/embeddings', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${openaiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: 'text-embedding-3-small',
        input: text,
        dimensions: 1536,
      }),
    })

    if (!response.ok) {
      console.error('OpenAI embedding error:', response.status)
      return null
    }

    const data = await response.json()
    return data.data?.[0]?.embedding ?? null
  } catch (err) {
    console.error('Embedding request failed:', err)
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
  const ip = request.headers.get('x-forwarded-for')?.split(',')[0]?.trim() ?? 'unknown'

  if (!checkRateLimit(ip)) {
    return NextResponse.json(
      { error: 'Rate limit exceeded. Try again in a minute.' },
      { status: 429 }
    )
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
    // Embed query in parallel with search (if OpenAI key is set)
    const queryEmbedding = await embedQuery(q)
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
