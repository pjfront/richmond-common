import { NextResponse, type NextRequest } from 'next/server'
import { getOperatorSession } from '@/lib/operator-auth'
import { logEvent, requestContext } from '@/lib/logger'

export async function POST(request: NextRequest) {
  const session = await getOperatorSession()
  session.destroy()
  logEvent('operator.logout', { ...requestContext(request) })
  return NextResponse.json({ ok: true })
}
