import { Metadata } from 'next'
import Link from 'next/link'
import { getTopicCounts } from '@/lib/queries'
import { RICHMOND_LOCAL_ISSUES } from '@/lib/local-issues'

export const metadata: Metadata = {
  title: 'Topics',
  description: 'Browse Richmond City Council agenda items by local issue, from Chevron and Point Molate to rent control and police reform.',
}

export default async function TopicsPage() {
  const topicCounts = await getTopicCounts()

  // Build a lookup from display label → count data
  const countsByLabel = new Map(topicCounts.map((t) => [t.topic_label, t]))

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-slate-900 mb-2">Topics</h1>
        <p className="text-slate-600">
          Richmond&rsquo;s defining local issues, tracked across every City Council meeting.
          Each topic collects the agenda items, votes, and public testimony
          that shape how the city handles these recurring questions.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {RICHMOND_LOCAL_ISSUES.map((issue) => {
          const counts = countsByLabel.get(issue.label)
          const itemCount = counts?.item_count ?? 0
          const latestDate = counts?.latest_meeting_date
          const formatted = latestDate
            ? new Date(latestDate + 'T12:00:00').toLocaleDateString('en-US', {
                month: 'short',
                year: 'numeric',
              })
            : null

          return (
            <Link
              key={issue.id}
              href={`/topics/${issue.id}`}
              className="block border border-slate-200 rounded-lg p-5 hover:border-civic-navy-light hover:bg-slate-50/50 transition-colors"
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <h2 className="text-base font-semibold text-slate-900">
                  {issue.label}
                </h2>
                <span className={`shrink-0 text-xs font-medium px-2 py-0.5 rounded-full ${issue.color}`}>
                  {itemCount}
                </span>
              </div>
              <p className="text-sm text-slate-600 line-clamp-2 mb-2">
                {issue.context}
              </p>
              {formatted && (
                <p className="text-xs text-slate-400">
                  Latest: {formatted}
                </p>
              )}
            </Link>
          )
        })}
      </div>
    </div>
  )
}
