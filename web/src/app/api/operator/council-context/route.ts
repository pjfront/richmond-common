import { NextResponse, type NextRequest } from 'next/server'
import { getEconomicInterests, getForm700Filings } from '@/lib/queries'
import { isUuid } from '@/lib/queries/_shared'
import { withOperatorAuth } from '@/lib/operator-auth'

export const dynamic = 'force-dynamic'

export const GET = withOperatorAuth(async (request: NextRequest) => {
  const officialId = request.nextUrl.searchParams.get('official_id') ?? ''
  if (!isUuid(officialId)) {
    return NextResponse.json({ error: 'Invalid official ID' }, { status: 400 })
  }

  const [interests, filings] = await Promise.all([
    getEconomicInterests(officialId),
    getForm700Filings(officialId),
  ])
  return NextResponse.json(
    { interests, filings },
    { headers: { 'Cache-Control': 'private, no-store' } },
  )
})
