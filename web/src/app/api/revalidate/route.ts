import { NextRequest, NextResponse } from 'next/server'
import { revalidatePath } from 'next/cache'

/**
 * On-demand ISR revalidation endpoint.
 *
 * Busts the ISR cache for specified paths so stale data doesn't
 * persist for up to an hour after data syncs.
 *
 * Usage:
 *   POST /api/revalidate
 *   Body: { "paths": ["/meetings", "/council"], "secret": "..." }
 *
 * Or revalidate all known pages:
 *   POST /api/revalidate
 *   Body: { "all": true, "secret": "..." }
 *
 * Protected by REVALIDATION_SECRET env var.
 */

const KNOWN_PATHS = [
  '/',
  '/meetings',
  '/council',
  '/elections',
  '/public-records',
  '/about',
  '/reports',
]

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({})) as Record<string, unknown>
  const secret = process.env.REVALIDATION_SECRET

  // If a secret is configured, require it
  if (secret && body.secret !== secret) {
    return NextResponse.json({ error: 'Invalid secret' }, { status: 401 })
  }

  // If no secret is configured, only allow from localhost/internal
  if (!secret) {
    const forwarded = request.headers.get('x-forwarded-for')
    const ip = forwarded?.split(',')[0]?.trim() ?? ''
    const isLocal = ip === '127.0.0.1' || ip === '::1' || ip === ''
    if (!isLocal) {
      return NextResponse.json(
        { error: 'REVALIDATION_SECRET not configured and request is not local' },
        { status: 401 }
      )
    }
  }

  const paths: string[] = body.all
    ? KNOWN_PATHS
    : Array.isArray(body.paths)
      ? (body.paths as string[]).filter((p): p is string => typeof p === 'string' && p.startsWith('/'))
      : []

  if (paths.length === 0) {
    return NextResponse.json(
      { error: 'Provide "paths" array or "all": true' },
      { status: 400 }
    )
  }

  const results: Record<string, string> = {}
  for (const path of paths) {
    try {
      revalidatePath(path)
      results[path] = 'revalidated'
    } catch (err) {
      results[path] = `error: ${err instanceof Error ? err.message : String(err)}`
    }
  }

  return NextResponse.json({ revalidated: results, timestamp: new Date().toISOString() })
}
