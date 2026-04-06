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

function voteLabel(outcome: SimilarItem['vote_outcome']): string {
  switch (outcome) {
    case 'passed': return 'Passed'
    case 'failed': return 'Failed'
    case 'upcoming': return 'Upcoming'
    case 'minutes pending': return 'Minutes pending'
    default: return 'No vote'
  }
}

function voteClasses(outcome: SimilarItem['vote_outcome']): string {
  switch (outcome) {
    case 'passed': return 'bg-green-50 text-vote-aye'
    case 'failed': return 'bg-red-50 text-vote-nay'
    case 'upcoming': return 'bg-blue-50 text-blue-600'
    case 'minutes pending': return 'bg-amber-50 text-amber-600'
    default: return 'bg-slate-100 text-slate-500'
  }
}

/**
 * Server component: finds semantically similar agenda items using
 * pgvector embeddings. Falls back gracefully when the source item
 * has no embedding (returns nothing, letting the parent render
 * the existing topic_label/category-based related items instead).
 */
export default async function SimilarDiscussions({
  itemId,
  limit = 5,
}: {
  itemId: string
  limit?: number
}) {
  const items = await findSimilarItems(itemId, { limit })

  if (items.length === 0) return null

  return (
    <div className="mb-6">
      <h2 className="text-lg font-semibold text-civic-navy mb-1">
        Similar Discussions
      </h2>
      <p className="text-xs text-slate-400 mb-3">
        {items.length} related item{items.length !== 1 ? 's' : ''} found by meaning
      </p>
      <div className="space-y-1.5">
        {items.map((si) => (
          <Link
            key={si.id}
            href={agendaItemPath(si.meeting_id, si.item_number)}
            className="flex items-center justify-between gap-3 py-2.5 px-3 rounded-lg border border-transparent hover:border-civic-navy/20 hover:bg-slate-50 transition-all group"
          >
            <div className="flex-1 min-w-0">
              <p className="text-sm text-slate-800 group-hover:text-civic-navy truncate">
                {si.summary_headline ?? si.title}
              </p>
              <div className="flex items-center gap-2 text-xs text-slate-400 group-hover:text-slate-500">
                <span>{formatShortDate(si.meeting_date)}</span>
                {si.financial_amount && (
                  <span className="text-civic-amber">{si.financial_amount}</span>
                )}
                {si.public_comment_count > 0 && (
                  <span>{si.public_comment_count} comment{si.public_comment_count !== 1 ? 's' : ''}</span>
                )}
                <span className="text-slate-300">
                  {Math.round(si.similarity * 100)}% match
                </span>
              </div>
            </div>
            <span className={`shrink-0 text-xs font-medium px-2 py-0.5 rounded ${voteClasses(si.vote_outcome)}`}>
              {voteLabel(si.vote_outcome)}
            </span>
          </Link>
        ))}
      </div>
    </div>
  )
}
