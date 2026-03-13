import { NextRequest, NextResponse } from 'next/server'
import { searchSite } from '@/lib/queries'
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

// ─── Validation ─────────────────────────────────────────────

const VALID_TYPES: SearchResultType[] = ['agenda_item', 'official', 'commission', 'vote_explainer']
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
    const results = await searchSite(q, {
      resultType: type ?? undefined,
      limit,
      offset,
    })

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
