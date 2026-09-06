import Link from 'next/link'
import { findSimilarItems } from '@/lib/queries'
import { agendaItemPath } from '@/lib/format'
import type { SimilarItem } from '@/lib/types'

function formatShortDate(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

/**
 * Server component: finds semantically similar agenda items using
 * pgvector embeddings. A source item without an embedding is a legitimate
 * empty state and renders nothing. Read failures intentionally escape this
 * force-static parent render: ISR retains its last successful page, while a
 * first render fails instead of caching a temporary fallback for 24 hours.
 */
export default async function SimilarDiscussions({
  itemId,
  limit = 5,
}: {
  itemId: string
  limit?: number
}) {
  const items: SimilarItem[] = await findSimilarItems(itemId, { limit })

  if (items.length === 0) return null

  return (
    <div className="mb-6">
      <h2 className="text-lg font-semibold text-civic-navy mb-1">
        Related agenda records
      </h2>
      <p className="text-sm text-slate-600 mb-3">
        Automatically matched by topic. Open an item to check its relevance and each motion’s outcome.
      </p>
      <div className="space-y-1.5">
        {items.map((si) => (
          <Link
            key={si.id}
            href={agendaItemPath(si.meeting_id, si.item_number)}
            className="flex items-center justify-between gap-3 py-2.5 px-3 rounded-lg border border-transparent hover:border-civic-navy/20 hover:bg-slate-50 transition-all group"
          >
            <div className="flex-1 min-w-0">
              <p className="text-sm text-slate-800 group-hover:text-civic-navy line-clamp-2">
                {si.title}
              </p>
              <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
                <span>{formatShortDate(si.meeting_date)}</span>
                {si.financial_amount && (
                  <span className="text-civic-amber">{si.financial_amount}</span>
                )}
                {si.public_comment_count > 0 && (
                  <span>{si.public_comment_count} comment{si.public_comment_count !== 1 ? 's' : ''} recorded</span>
                )}
              </div>
            </div>
            <span className="shrink-0 text-civic-navy" aria-hidden="true">→</span>
          </Link>
        ))}
      </div>
    </div>
  )
}
