import { NextResponse, type NextRequest } from 'next/server'
import { getIronSession } from 'iron-session'
import { getOperatorSessionOptions, type OperatorSession } from '@/lib/operator-session'

const PUBLIC_OPERATOR_PATHS = new Set(['/operator/login'])

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  if (!pathname.startsWith('/operator')) {
    return NextResponse.next()
  }

  if (PUBLIC_OPERATOR_PATHS.has(pathname)) {
    return NextResponse.next()
  }

  const res = NextResponse.next()
  const session = await getIronSession<OperatorSession>(
    request,
    res,
    getOperatorSessionOptions(),
  )

  if (!session.isOperator) {
    const loginUrl = new URL('/operator/login', request.url)
    loginUrl.searchParams.set('next', pathname)
    return NextResponse.redirect(loginUrl)
  }

  return res
}

export const config = {
  matcher: ['/operator/:path*'],
}
