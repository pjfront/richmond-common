import { NextResponse } from 'next/server'
import { isOperatorAuthenticated } from '@/lib/operator-auth'

export async function GET() {
  const isOperator = await isOperatorAuthenticated()
  return NextResponse.json(
    { isOperator },
    { headers: { 'Cache-Control': 'no-store' } },
  )
}
