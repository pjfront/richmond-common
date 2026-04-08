import { NextRequest, NextResponse } from 'next/server'
import { revalidatePath } from 'next/cache'

/**
 * On-demand ISR revalidation endpoint.
 *
 * Forces Next.js to regenerate a cached page immediately, bypassing
 * the 1-hour ISR timer. Useful after deploys that cache stale data.
 *
 * Usage:
 *   POST /api/revalidate
 *   Body: { "path": "/meetings", "secret": "<REVALIDATION_SECRET>" }
 *
 * Or revalidate all common pages:
 *   POST /api/revalidate
 *   Body: { "path": "all", "secret": "<REVALIDATION_SECRET>" }
 */
export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}))
  const { path, secret } = body as { path?: string; secret?: string }

  // Validate secret
  const expectedSecret = process.env.REVALIDATION_SECRET
  if (!expectedSecret) {
    return NextResponse.json(
      { error: 'REVALIDATION_SECRET not configured' },
      { status: 500 },
    )
  }
  if (secret !== expectedSecret) {
    return NextResponse.json({ error: 'Invalid secret' }, { status: 401 })
  }

  if (!path) {
    return NextResponse.json({ error: 'Missing path' }, { status: 400 })
  }

  const revalidated: string[] = []

  if (path === 'all') {
    // Revalidate all common ISR pages
    const paths = [
      '/meetings',
      '/council',
      '/elections',
      '/public-records',
      '/reports',
      '/',
    ]
    for (const p of paths) {
      revalidatePath(p)
      revalidated.push(p)
    }
  } else {
    revalidatePath(path)
    revalidated.push(path)
  }

  return NextResponse.json({
    revalidated,
    timestamp: new Date().toISOString(),
  })
}
