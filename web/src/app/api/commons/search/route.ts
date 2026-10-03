import { NextRequest, NextResponse } from 'next/server'
import { CommonsSearchInputError, planCommonsSearch } from '@/lib/commons-search'
import { searchCommons } from '@/lib/queries/commons-search'

export async function GET(request: NextRequest) {
  try {
    const plan = planCommonsSearch(request.nextUrl.searchParams)
    const result = await searchCommons(plan)
    return NextResponse.json(result, { headers: { 'Cache-Control': 'private, no-store' } })
  } catch (error) {
    if (error instanceof CommonsSearchInputError) {
      return NextResponse.json({ error: error.message }, { status: 400, headers: { 'Cache-Control': 'no-store' } })
    }
    console.error('Commons staging search unavailable:', error instanceof Error ? error.name : 'read failure')
    return NextResponse.json({ error: 'The source records could not be loaded. Please try again later.' },
      { status: 503, headers: { 'Cache-Control': 'no-store', 'Retry-After': '60' } })
  }
}
