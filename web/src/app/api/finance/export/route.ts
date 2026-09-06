import { getPublicFinanceSnapshot } from '@/lib/queries/finance-public'
import { filterFinanceEvents, financeCsv } from '@/lib/finance-ledger'

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams
  try {
    const snapshot = await getPublicFinanceSnapshot()
    if (snapshot.truncated) return Response.json({ error: 'The complete export is temporarily unavailable.' }, { status: 503 })
    const events = filterFinanceEvents(snapshot.events, params.get('q') ?? '', params.get('committee') ?? '')
    return new Response(financeCsv(events), { headers: {
      'Content-Type': 'text/csv; charset=utf-8',
      'Content-Disposition': 'attachment; filename="richmond-reported-finance-2026.csv"',
      'Cache-Control': 'public, max-age=900',
      'X-Content-Type-Options': 'nosniff',
    } })
  } catch {
    return Response.json({ error: 'Campaign records could not be loaded. Please try again later.' }, { status: 503 })
  }
}
