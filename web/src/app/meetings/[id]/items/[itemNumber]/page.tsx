import { notFound } from 'next/navigation'
import Link from 'next/link'
import type { Metadata } from 'next'
import { getAgendaItemDetail } from '@/lib/queries'
import type { RelatedTopicItem } from '@/lib/types'
import { agendaItemPath } from '@/lib/format'
import CategoryBadge from '@/components/CategoryBadge'
import TopicLabel from '@/components/TopicLabel'
import VoteBreakdown from '@/components/VoteBreakdown'
import ExpandableOfficialText from '@/components/ExpandableOfficialText'
import FormattedDescription from '@/components/FormattedDescription'
import CommentBreakdownSection from '@/components/CommentBreakdownSection'
import OperatorGate from '@/components/OperatorGate'

export const dynamic = 'force-dynamic'
export const revalidate = 3600

interface ItemPageProps {
  params: Promise<{ id: string; itemNumber: string }>
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

function formatShortDate(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

export async function generateMetadata({ params }: ItemPageProps): Promise<Metadata> {
  const { id, itemNumber } = await params
  const item = await getAgendaItemDetail(id, decodeURIComponent(itemNumber))
  if (!item) return { title: 'Item Not Found' }

  const title = item.summary_headline ?? item.title
  const dateStr = formatDate(item.meeting_date)
  return {
    title: `${title} — ${dateStr}`,
    description: item.plain_language_summary
      ?? `Agenda item ${item.item_number} from the Richmond City Council meeting on ${dateStr}.`,
    openGraph: {
      title: `${title} | Richmond Commons`,
      description: item.plain_language_summary
        ?? `Agenda item from ${dateStr} council meeting.`,
      type: 'article',
    },
  }
}

export default async function AgendaItemDetailPage({ params }: ItemPageProps) {
  const { id, itemNumber } = await params
  const item = await getAgendaItemDetail(id, decodeURIComponent(itemNumber))
  if (!item) notFound()

  const dateStr = formatDate(item.meeting_date)
  const hasDescription = item.description && item.description.length > 0
  const hasSummary = !!item.plain_language_summary

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      {/* Breadcrumb */}
      <nav className="mb-6 text-sm text-slate-500">
        <Link href="/meetings" className="text-civic-navy-light hover:text-civic-navy">
          Meetings
        </Link>
        {' › '}
        <Link
          href={`/meetings/${item.meeting_id}`}
          className="text-civic-navy-light hover:text-civic-navy"
        >
          {dateStr}
        </Link>
        {' › '}
        <span className="text-slate-700">Item {item.item_number}</span>
      </nav>

      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl sm:text-3xl font-bold text-civic-navy leading-snug mb-3">
          {item.summary_headline ?? item.title}
        </h1>

        <div className="flex flex-wrap items-center gap-2 mb-3">
          {item.topic_label && <TopicLabel label={item.topic_label} />}
          {item.category && <CategoryBadge category={item.category} />}
          {item.department && (
            <span className="text-xs text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
              {item.department}
            </span>
          )}
          {item.was_pulled_from_consent && (
            <span className="text-xs text-civic-amber font-medium bg-civic-amber/10 px-2 py-0.5 rounded">
              Pulled from consent
            </span>
          )}
        </div>

        {item.financial_amount && (
          <p className="text-base font-medium text-civic-amber mb-3">
            {item.financial_amount}
          </p>
        )}

        {item.resolution_number && (
          <p className="text-xs text-slate-400 mb-2">
            Resolution {item.resolution_number}
          </p>
        )}
      </div>

      {/* Plain language summary */}
      {hasSummary && (
        <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 mb-6">
          <p className="text-xs font-medium text-slate-500 mb-1.5">In Plain English</p>
          <p className="text-base text-slate-700 leading-relaxed">
            {item.plain_language_summary}
          </p>
          <p className="text-[10px] text-slate-400 mt-2">
            Auto-generated summary. Source: official agenda documents.
          </p>
        </div>
      )}

      {/* Official agenda text */}
      {hasDescription && (
        <div className="mb-6">
          {hasSummary ? (
            <ExpandableOfficialText title={item.title} description={item.description} />
          ) : (
            <div>
              <p className="text-xs font-medium text-slate-500 mb-1">Official Agenda Text</p>
              <FormattedDescription description={item.description} />
            </div>
          )}
        </div>
      )}

      {/* Votes */}
      {item.motions.length > 0 && (
        <div className="mb-6">
          <h2 className="text-lg font-semibold text-civic-navy mb-3">Votes</h2>
          <div className="space-y-3">
            {item.motions.map((motion) => (
              <VoteBreakdown key={motion.id} motion={motion} />
            ))}
          </div>
        </div>
      )}

      {/* Public comments */}
      {item.comments.length > 0 && (
        <div className="mb-6">
          <CommentBreakdownSection
            comments={item.comments}
            spokenCount={item.spoken_comment_count}
            writtenCount={item.written_comment_count}
          />
        </div>
      )}

      {/* Related items (continued from/to) */}
      {(item.continued_from_item || item.continued_to_item) && (
        <div className="mb-6">
          <h2 className="text-lg font-semibold text-civic-navy mb-3">Related Items</h2>
          <div className="space-y-2">
            {item.continued_from_item && (
              <Link
                href={agendaItemPath(item.continued_from_item.meeting_id, item.continued_from_item.item_number)}
                className="block text-sm text-civic-navy-light hover:text-civic-navy hover:underline"
              >
                Continued from: {item.continued_from_item.title}
                <span className="text-xs text-slate-400 ml-2">
                  ({formatShortDate(item.continued_from_item.meeting_date)})
                </span>
              </Link>
            )}
            {item.continued_to_item && (
              <Link
                href={agendaItemPath(item.continued_to_item.meeting_id, item.continued_to_item.item_number)}
                className="block text-sm text-civic-navy-light hover:text-civic-navy hover:underline"
              >
                Continued to: {item.continued_to_item.title}
                <span className="text-xs text-slate-400 ml-2">
                  ({formatShortDate(item.continued_to_item.meeting_date)})
                </span>
              </Link>
            )}
          </div>
        </div>
      )}

      {/* Conflict flags — operator only */}
      <OperatorGate>
        {item.conflict_flags.length > 0 && (
          <div className="bg-civic-amber/10 border border-civic-amber/30 rounded-lg p-4 mb-6">
            <h3 className="font-semibold text-civic-amber">
              {item.conflict_flags.length} Campaign Contribution{' '}
              {item.conflict_flags.length !== 1 ? 'Records' : 'Record'} Identified
            </h3>
            <p className="text-sm text-slate-700 mt-1">
              The scanner found overlaps between this item, campaign contributions, and financial disclosures.
              A campaign contribution does not imply wrongdoing.
            </p>
            <Link
              href={`/influence/item/${item.id}`}
              className="text-sm text-civic-amber hover:underline mt-2 inline-block"
            >
              View detailed influence map →
            </Link>
          </div>
        )}
      </OperatorGate>

      {/* Related items by topic and/or category */}
      {item.related_topic_items.length > 0 && (() => {
        const topicItems = item.related_topic_items.filter((ri) => ri.match_tier <= 2)
        const categoryItems = item.related_topic_items.filter((ri) => ri.match_tier === 3)

        function RelatedItemLink({ ri }: { ri: RelatedTopicItem }) {
          return (
            <Link
              key={ri.id}
              href={agendaItemPath(ri.meeting_id, ri.item_number)}
              className="flex items-center justify-between gap-3 py-2.5 px-3 rounded-lg border border-transparent hover:border-civic-navy/20 hover:bg-slate-50 transition-all group"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm text-slate-800 group-hover:text-civic-navy truncate">
                  {ri.summary_headline ?? ri.title}
                </p>
                <p className="text-xs text-slate-400 group-hover:text-slate-500">
                  {formatShortDate(ri.meeting_date)}
                </p>
              </div>
              <span className={`shrink-0 text-xs font-medium px-2 py-0.5 rounded ${
                ri.vote_outcome === 'passed'
                  ? 'bg-green-50 text-vote-aye'
                  : ri.vote_outcome === 'failed'
                    ? 'bg-red-50 text-vote-nay'
                    : ri.vote_outcome === 'upcoming'
                      ? 'bg-blue-50 text-blue-600'
                      : ri.vote_outcome === 'minutes pending'
                        ? 'bg-amber-50 text-amber-600'
                        : 'bg-slate-100 text-slate-500'
              }`}>
                {ri.vote_outcome === 'upcoming' ? 'Upcoming' :
                 ri.vote_outcome === 'minutes pending' ? 'Minutes pending' :
                 ri.vote_outcome === 'no vote' ? 'No vote' :
                 ri.vote_outcome === 'passed' ? 'Passed' : 'Failed'}
              </span>
            </Link>
          )
        }

        return (
          <div className="mb-6">
            <h2 className="text-lg font-semibold text-civic-navy mb-3">
              Related Items
            </h2>
            {topicItems.length > 0 && (
              <div className="space-y-1.5">
                {topicItems.map((ri) => <RelatedItemLink key={ri.id} ri={ri} />)}
              </div>
            )}
            {categoryItems.length > 0 && (
              <div className={topicItems.length > 0 ? 'mt-4' : ''}>
                <div className="space-y-1.5">
                  {categoryItems.map((ri) => <RelatedItemLink key={ri.id} ri={ri} />)}
                </div>
              </div>
            )}
          </div>
        )
      })()}

      {/* Back to meeting */}
      <div className="mt-8 pt-6 border-t border-slate-200">
        <Link
          href={`/meetings/${item.meeting_id}`}
          className="text-sm text-civic-navy-light hover:text-civic-navy"
        >
          ← View full {dateStr} meeting
        </Link>
        {item.meeting_agenda_url && (
          <span className="mx-2 text-slate-300">|</span>
        )}
        {item.meeting_agenda_url && (
          <a
            href={item.meeting_agenda_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-civic-navy-light hover:text-civic-navy hover:underline"
          >
            View official agenda →
          </a>
        )}
      </div>

      {/* Prev / Next item navigation */}
      {(item.prev_item || item.next_item) && (
        <div className="mt-4 flex items-stretch gap-3">
          {item.prev_item ? (
            <Link
              href={agendaItemPath(item.meeting_id, item.prev_item.item_number)}
              className="flex-1 text-left p-3 rounded-md border border-slate-200 hover:bg-slate-50 transition-colors group"
            >
              <p className="text-[10px] font-medium text-slate-400 uppercase tracking-wide mb-0.5">
                ← Previous
              </p>
              <p className="text-sm text-slate-700 group-hover:text-civic-navy line-clamp-1">
                {item.prev_item.summary_headline ?? item.prev_item.title}
              </p>
            </Link>
          ) : (
            <div className="flex-1" />
          )}
          {item.next_item ? (
            <Link
              href={agendaItemPath(item.meeting_id, item.next_item.item_number)}
              className="flex-1 text-right p-3 rounded-md border border-slate-200 hover:bg-slate-50 transition-colors group"
            >
              <p className="text-[10px] font-medium text-slate-400 uppercase tracking-wide mb-0.5">
                Next →
              </p>
              <p className="text-sm text-slate-700 group-hover:text-civic-navy line-clamp-1">
                {item.next_item.summary_headline ?? item.next_item.title}
              </p>
            </Link>
          ) : (
            <div className="flex-1" />
          )}
        </div>
      )}
    </div>
  )
}
