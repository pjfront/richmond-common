import { NextResponse, type NextRequest } from 'next/server'
import { getIronSession } from 'iron-session'
import { getOperatorSessionOptions, type OperatorSession } from '@/lib/operator-session'
import { protectSiteResponse, siteAccessResponse } from '@/lib/site-access'

const PUBLIC_OPERATOR_PATHS = new Set(['/operator/login'])

export async function middleware(request: NextRequest) {
  const accessResponse = await siteAccessResponse(request)
  if (accessResponse) return accessResponse
  const { pathname } = request.nextUrl
  const res = protectSiteResponse(NextResponse.next())

  if (!pathname.startsWith('/operator')) {
    return res
  }

  if (PUBLIC_OPERATOR_PATHS.has(pathname)) {
    return res
  }

  const session = await getIronSession<OperatorSession>(
    request,
    res,
    getOperatorSessionOptions(),
  )

  if (!session.isOperator) {
    const loginUrl = new URL('/operator/login', request.url)
    loginUrl.searchParams.set('next', pathname)
    return protectSiteResponse(NextResponse.redirect(loginUrl))
  }

  return res
}

export const config = {
  // Include assets, API/export routes, RSC and prefetch requests. A route or
  // extension exclusion here would bypass the private-preview boundary.
  matcher: ['/:path*'],
}
