import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { getAgendaItemsByCategory } from '@/lib/queries'
import { agendaItemPath } from '@/lib/format'
import CategoryBadge from '@/components/CategoryBadge'
import MeetingTypeBadge from '@/components/MeetingTypeBadge'
import LastUpdated from '@/components/LastUpdated'


interface CategoryPageProps {
  params: Promise<{ slug: string }>
}

export async function generateMetadata({ params }: CategoryPageProps): Promise<Metadata> {
  const { slug } = await params
  const label = slug.charAt(0).toUpperCase() + slug.slice(1)
  return {
    title: `${label} — Agenda Items`,
    description: `All Richmond City Council agenda items categorized as ${label}.`,
  }
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

/**
 * Category Drill-Through Page (S14-B6)
 *
 * Shows all agenda items in a single category across all meetings.
 * Route: /meetings/category/[slug]
 */
export default async function CategoryPage({ params }: CategoryPageProps) {
  const { slug } = await params
  const items = await getAgendaItemsByCategory(slug)

  if (items.length === 0) {
    notFound()
  }

  const label = slug.charAt(0).toUpperCase() + slug.slice(1)

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <nav className="mb-6">
        <Link
          href="/meetings"
          className="text-sm text-civic-navy hover:underline"
        >
          &larr; All Meetings
        </Link>
      </nav>

      <div className="flex items-center gap-3 mb-2">
        <CategoryBadge category={slug} />
        <h1 className="text-3xl font-bold text-civic-navy">{label}</h1>
      </div>
      <p className="text-slate-600 mb-6">
        {items.length} agenda {items.length === 1 ? 'item' : 'items'} across all council meetings.
      </p>

      <div className="space-y-3">
        {items.map((item) => (
          <Link
            key={item.id}
            href={agendaItemPath(item.meeting_id, item.item_number)}
            className="block bg-white rounded-lg border border-slate-200 p-4 hover:border-slate-300 hover:shadow-sm transition-all"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                {item.summary_headline ? (
                  <>
                    <h3 className="font-semibold text-slate-900">
                      {item.summary_headline}
                    </h3>
                    <p className="text-sm text-slate-500 mt-0.5 line-clamp-2">
                      {item.title}
                    </p>
                  </>
                ) : (
                  <h3 className="font-semibold text-slate-900 line-clamp-2">
                    {item.title}
                  </h3>
                )}

                {item.plain_language_summary && (
                  <p className="text-sm text-slate-600 mt-1 line-clamp-2">
                    {item.plain_language_summary}
                  </p>
                )}
              </div>

              {item.financial_amount && (
                <span className="text-sm font-medium text-civic-amber shrink-0">
                  {item.financial_amount}
                </span>
              )}
            </div>

            <div className="flex items-center gap-3 mt-2 text-xs text-slate-500">
              <span>{formatDate(item.meeting_date)}</span>
              <MeetingTypeBadge meetingType={item.meeting_type} compact />
              <span className="text-slate-300">|</span>
              <span>Item {item.item_number}</span>
              {item.was_pulled_from_consent && (
                <span className="text-civic-amber font-medium">Pulled from consent</span>
              )}
            </div>
          </Link>
        ))}
      </div>

      <LastUpdated />
    </div>
  )
}
