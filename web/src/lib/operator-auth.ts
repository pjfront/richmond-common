import { NextResponse, type NextRequest } from 'next/server'
import { getIronSession, type IronSession } from 'iron-session'
import { cookies } from 'next/headers'
import { getOperatorSessionOptions, type OperatorSession } from './operator-session'

export async function getOperatorSession(): Promise<IronSession<OperatorSession>> {
  const store = await cookies()
  return getIronSession<OperatorSession>(store, getOperatorSessionOptions())
}

export async function isOperatorAuthenticated(): Promise<boolean> {
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
