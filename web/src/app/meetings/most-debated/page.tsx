import { Metadata } from 'next'
import Link from 'next/link'
import { getControversialItems } from '@/lib/queries'
export const metadata: Metadata = {
  title: 'Most Debated',
  description: 'The most contentious votes and public testimony in Richmond City Council meetings.',
}

export default async function MostDebatedPage() {
  return <MostDebatedContent />
}

async function MostDebatedContent() {
  const items = await getControversialItems(30)

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-slate-900 mb-2">Most Debated</h1>
        <p className="text-slate-600">
          Agenda items that drew the most public testimony, split votes, or multiple motions
          across all Richmond City Council meetings.
        </p>
      </div>

      {items.length === 0 ? (
        <p className="text-slate-500 italic">No controversial items found.</p>
      ) : (
        <div className="space-y-4">
          {items.map((item) => {
            const date = new Date(item.meeting_date + 'T12:00:00')
            const formatted = date.toLocaleDateString('en-US', {
              year: 'numeric',
              month: 'long',
              day: 'numeric',
            })

            // Narrative framing per D6: describe why it was contentious
            const reasons: string[] = []
            if (item.vote_tally) {
              reasons.push(
                item.result === 'failed'
                  ? `Failed (${item.vote_tally})`
                  : `Split vote (${item.vote_tally})`,
              )
            }
            if (item.public_comment_count > 0) {
              reasons.push(
                `${item.public_comment_count} public comment${item.public_comment_count === 1 ? '' : 's'}`,
              )
            }
            if (item.motion_count > 1) {
              reasons.push(`${item.motion_count} motions`)
            }

            return (
              <Link
                key={item.agenda_item_id}
                href={`/meetings/${item.meeting_id}`}
                className="block border border-slate-200 rounded-lg p-5 hover:border-civic-navy-light hover:bg-slate-50/50 transition-colors"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-slate-500 mb-1">
                      {formatted} &middot; Item {item.item_number}
                    </p>
                    <h2 className="text-base font-semibold text-slate-900 mb-2 line-clamp-2">
                      {item.title}
                    </h2>
                    {reasons.length > 0 && (
                      <p className="text-sm text-slate-600">
                        {reasons.join(' · ')}
                      </p>
                    )}
                  </div>
                  {item.result && (
                    <span
                      className={`shrink-0 text-xs font-medium px-2.5 py-1 rounded-full ${
                        item.result === 'passed'
                          ? 'bg-emerald-100 text-emerald-800'
                          : item.result === 'failed'
                            ? 'bg-red-100 text-red-800'
                            : 'bg-slate-100 text-slate-600'
                      }`}
                    >
                      {item.result.charAt(0).toUpperCase() + item.result.slice(1)}
                    </span>
                  )}
                </div>
              </Link>
            )
          })}
        </div>
      )}

      <p className="text-xs text-slate-400 mt-8">
        Controversy ranking considers split votes, number of nay votes, public comment volume,
        and multiple motions on a single item. AI-assisted analysis of official meeting records.
      </p>
    </div>
  )
}
