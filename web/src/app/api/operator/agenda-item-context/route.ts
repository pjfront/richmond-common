import { NextResponse, type NextRequest } from 'next/server'
import { getItemInfluenceMapData } from '@/lib/queries'
import { isUuid } from '@/lib/queries/_shared'
import { withOperatorAuth } from '@/lib/operator-auth'

export const dynamic = 'force-dynamic'

export const GET = withOperatorAuth(async (request: NextRequest) => {
  const agendaItemId = request.nextUrl.searchParams.get('agenda_item_id') ?? ''
  if (!isUuid(agendaItemId)) {
    return NextResponse.json({ error: 'Invalid agenda item ID' }, { status: 400 })
  }

  const data = await getItemInfluenceMapData(agendaItemId)
  return NextResponse.json(
    { data },
    { headers: { 'Cache-Control': 'private, no-store' } },
  )
})
