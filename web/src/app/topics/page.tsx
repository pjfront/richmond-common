import { Metadata } from 'next'
import Link from 'next/link'
import { getPromotedTopics, TOPIC_PROMOTION_MIN_ITEMS, TOPIC_PROMOTION_MIN_MEETINGS } from '@/lib/queries'

export const metadata: Metadata = {
  title: 'Topics',
  description: 'Browse Richmond City Council agenda items by recurring topic, from labor and housing to environment and policing.',
}

function formatLatest(date: string): string {
  return new Date(date + 'T12:00:00').toLocaleDateString('en-US', {
    month: 'short',
    year: 'numeric',
  })
}

export default async function TopicsPage() {
  const topics = await getPromotedTopics()

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-slate-900 mb-2">Topics</h1>
        <p className="text-slate-600">
          Recurring topics across Richmond City Council meetings. A topic surfaces here once it&rsquo;s
          been discussed on at least {TOPIC_PROMOTION_MIN_ITEMS} agenda items spread across
          {' '}{TOPIC_PROMOTION_MIN_MEETINGS} or more meetings — one-off matters stay on their
          meetings without crowding this index.
        </p>
      </div>

      {topics.length === 0 ? (
        <p className="text-slate-500 italic">
          No recurring topics yet. As more meetings are processed, topics that show up across multiple
          agenda items will appear here.
        </p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {topics.map((topic) => (
            <Link
              key={topic.slug}
              href={`/topics/${topic.slug}`}
              className="block border border-slate-200 rounded-lg p-5 hover:border-civic-navy-light hover:bg-slate-50/50 transition-colors"
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <h2 className="text-base font-semibold text-slate-900">
                  {topic.label}
                </h2>
                <span className="shrink-0 text-xs font-medium px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 tabular-nums">
                  {topic.item_count}
                </span>
              </div>
              <p className="text-sm text-slate-600">
                {topic.item_count} item{topic.item_count === 1 ? '' : 's'} across {topic.meeting_count} meeting{topic.meeting_count === 1 ? '' : 's'}
              </p>
              <p className="text-xs text-slate-400 mt-1">
                Latest: {formatLatest(topic.latest_meeting_date)}
              </p>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
