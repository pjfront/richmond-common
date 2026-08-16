import { NextResponse, type NextRequest } from 'next/server'
import { getConflictFlagsDetailed } from '@/lib/queries'
import { isUuid } from '@/lib/queries/_shared'
import { withOperatorAuth } from '@/lib/operator-auth'

export const dynamic = 'force-dynamic'

export const GET = withOperatorAuth(async (request: NextRequest) => {
  const meetingId = request.nextUrl.searchParams.get('meeting_id') ?? ''
  if (!isUuid(meetingId)) {
    return NextResponse.json({ error: 'Invalid meeting ID' }, { status: 400 })
  }

  const flags = await getConflictFlagsDetailed(meetingId)
  return NextResponse.json(
    { flags },
    { headers: { 'Cache-Control': 'private, no-store' } },
  )
})
