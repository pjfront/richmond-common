import Link from 'next/link'
import type { MostDiscussedItem } from '@/lib/queries'
import TopicLabel from './TopicLabel'

function formatDate(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

interface MostDiscussedItemsProps {
  items: MostDiscussedItem[]
}

export default function MostDiscussedItems({ items }: MostDiscussedItemsProps) {
  if (items.length === 0) return null

  return (
    <section className="mb-10">
      <h2 className="text-xl font-semibold text-slate-800 mb-4">Most Discussed at City Hall</h2>
      <div className="space-y-3">
        {items.map((item) => (
          <Link
            key={item.agenda_item_id}
            href={`/meetings/${item.meeting_id}`}
            className="block bg-white rounded-lg border border-slate-200 border-l-4 border-l-civic-amber p-4 hover:border-slate-300 hover:shadow-sm transition-all"
          >
            <h3 className="font-semibold text-base text-slate-900 leading-snug">
              {item.summary_headline ?? item.title}
            </h3>
            <div className="flex items-center gap-2 mt-2 flex-wrap">
              <span className="text-xs font-medium text-civic-amber border border-civic-amber/30 rounded px-1.5 py-0.5">
                {item.public_comment_count} public {item.public_comment_count === 1 ? 'speaker' : 'speakers'}
              </span>
              {item.topic_label && <TopicLabel label={item.topic_label} />}
              <span className="text-xs text-slate-400 ml-auto">{formatDate(item.meeting_date)}</span>
            </div>
          </Link>
        ))}
      </div>
    </section>
  )
}
