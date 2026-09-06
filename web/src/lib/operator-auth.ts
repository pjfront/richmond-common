import { NextResponse, type NextRequest } from 'next/server'
import { getIronSession, type IronSession } from 'iron-session'
import { cookies } from 'next/headers'
import { getOperatorSessionOptions, type OperatorSession } from './operator-session'

export async function getOperatorSession(): Promise<IronSession<OperatorSession>> {
  const store = await cookies()
  return getIronSession<OperatorSession>(store, getOperatorSessionOptions())
}

export async function isOperatorAuthenticated(): Promise<boolean> {
  // Data-less Vercel Previews deliberately do not receive the production
  // session secret. Treat that exact platform boundary as anonymous so public
  // pages, the session probe, and operator-gated 404s remain testable without
  // copying a production credential into a Preview. Every other production
  // environment still reaches getOperatorSessionOptions(), which fails closed
  // when the required secret is missing.
  if (
    process.env.VERCEL_ENV === 'preview'
    && !process.env.IRON_SESSION_PASSWORD
  ) return false

  const session = await getOperatorSession()
  return session.isOperator === true
}

type RouteHandler<TArgs extends unknown[]> = (
  request: NextRequest,
  ...args: TArgs
) => Promise<Response> | Response

export function withOperatorAuth<TArgs extends unknown[]>(
  handler: RouteHandler<TArgs>,
): RouteHandler<TArgs> {
  return async (request, ...args) => {
    if (!(await isOperatorAuthenticated())) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }
    return handler(request, ...args)
  }
}
