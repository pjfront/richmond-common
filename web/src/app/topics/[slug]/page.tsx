import { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { getTopicItems } from '@/lib/queries'
import { RICHMOND_LOCAL_ISSUES } from '@/lib/local-issues'
// Build lookup once at module level
const issueById = new Map(RICHMOND_LOCAL_ISSUES.map((i) => [i.id, i]))

interface Props {
  params: Promise<{ slug: string }>
}

export async function generateStaticParams() {
  return RICHMOND_LOCAL_ISSUES.map((issue) => ({ slug: issue.id }))
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params
  const issue = issueById.get(slug)
  if (!issue) return { title: 'Topic Not Found' }
  return {
    title: issue.label,
    description: `${issue.context} Browse all related Richmond City Council agenda items.`,
  }
}

export default async function TopicDetailPage({ params }: Props) {
  return <TopicDetailContent params={params} />
}

async function TopicDetailContent({ params }: Props) {
  const { slug } = await params
  const issue = issueById.get(slug)
  if (!issue) notFound()

  const items = await getTopicItems(issue.label, 100)

  // Group items by meeting date for timeline display
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
        <h1 className="text-3xl font-bold text-slate-900 mb-2">{issue.label}</h1>
        <p className="text-slate-600">{issue.context}</p>
        <p className="text-sm text-slate-500 mt-2">
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
