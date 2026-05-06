import { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { getPromotedTopics, getTopicItems } from '@/lib/queries'

interface Props {
  params: Promise<{ slug: string }>
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params
  const topics = await getPromotedTopics()
  const topic = topics.find((t) => t.slug === slug)
  if (!topic) return { title: 'Topic Not Found' }
  return {
    title: topic.label,
    description: `Richmond City Council agenda items tagged with "${topic.label}", across ${topic.meeting_count} meeting${topic.meeting_count === 1 ? '' : 's'}.`,
  }
}

export default async function TopicDetailPage({ params }: Props) {
  const { slug } = await params
  const topics = await getPromotedTopics()
  const topic = topics.find((t) => t.slug === slug)
  if (!topic) notFound()

  const items = await getTopicItems(topic.label, 100)

  const grouped = new Map<string, typeof items>()
  for (const item of items) {
    const key = item.meeting_date
    const group = grouped.get(key)
    if (group) {
      group.push(item)
    } else {
      grouped.set(key, [item])
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <Link href="/topics" className="text-sm text-civic-navy-light hover:text-civic-navy mb-2 inline-block">
          &larr; All Topics
        </Link>
        <h1 className="text-3xl font-bold text-slate-900 mb-2">{topic.label}</h1>
        <p className="text-sm text-slate-500">
          {items.length} agenda item{items.length === 1 ? '' : 's'} across {grouped.size} meeting{grouped.size === 1 ? '' : 's'}
        </p>
      </div>

      {items.length === 0 ? (
        <p className="text-slate-500 italic">No agenda items tagged with this topic yet.</p>
      ) : (
        <div className="space-y-8">
          {Array.from(grouped.entries()).map(([date, dateItems]) => {
            const formatted = new Date(date + 'T12:00:00').toLocaleDateString('en-US', {
              weekday: 'long',
              year: 'numeric',
              month: 'long',
              day: 'numeric',
            })

            return (
              <div key={date}>
                <h2 className="text-sm font-medium text-slate-500 uppercase tracking-wide mb-3 border-b border-slate-200 pb-2">
                  {formatted}
                </h2>
                <div className="space-y-3">
                  {dateItems.map((item) => (
                    <Link
                      key={item.id}
                      href={`/meetings/${item.meeting_id}`}
                      className="block border border-slate-200 rounded-lg p-4 hover:border-civic-navy-light hover:bg-slate-50/50 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <p className="text-xs text-slate-400 mb-1">Item {item.item_number}</p>
                          <h3 className="text-sm font-semibold text-slate-900 mb-1 line-clamp-2">
                            {item.title}
                          </h3>
                          {item.summary_headline && (
                            <p className="text-sm text-slate-600 line-clamp-2">
                              {item.summary_headline}
                            </p>
                          )}
                          <div className="flex items-center gap-3 mt-2 text-xs text-slate-500">
                            {item.category && <span>{item.category}</span>}
                            {item.financial_amount && (
                              <span className="text-civic-amber">{item.financial_amount}</span>
                            )}
                            {item.public_comment_count > 0 && (
                              <span>{item.public_comment_count} comment{item.public_comment_count === 1 ? '' : 's'}</span>
                            )}
                          </div>
                        </div>
                      </div>
                    </Link>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
