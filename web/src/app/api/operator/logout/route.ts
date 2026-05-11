import { NextResponse } from 'next/server'
import { getOperatorSession } from '@/lib/operator-auth'

export async function POST() {
  const session = await getOperatorSession()
  session.destroy()
  return NextResponse.json({ ok: true })
}
