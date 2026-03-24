import { notFound } from 'next/navigation'
import Link from 'next/link'
import type { Metadata } from 'next'
import { getItemInfluenceMapData, getAgendaItemBasic } from '@/lib/queries'
import ExpandableOfficialText from '@/components/ExpandableOfficialText'
import ContributionNarrative from '@/components/ContributionNarrative'
import BehstedPaymentNarrative from '@/components/BehstedPaymentNarrative'
import { CampaignFinanceDisclaimer, BehstedPaymentDisclaimer, ConfidenceExplanation } from '@/components/InfluenceDisclaimer'
import EntityTypeIndicator from '@/components/EntityTypeIndicator'
import CategoryBadge from '@/components/CategoryBadge'
import SourceBadge from '@/components/SourceBadge'
import OperatorGate from '@/components/OperatorGate'
import RecordVisit from '@/components/RecordVisit'

export const revalidate = 3600

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

export async function generateMetadata(
  { params }: { params: Promise<{ id: string }> }
): Promise<Metadata> {
  const { id } = await params
  const item = await getAgendaItemBasic(id)
  if (!item) return { title: 'Item Not Found' }

  const title = item.summary_headline ?? item.title
  return {
    title: `Campaign Finance Context: ${title}`,
    description: `Campaign contribution records related to "${title}" from the ${formatDate(item.meeting_date)} council meeting.`,
  }
}

export default async function ItemInfluenceMapPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params

  return (
    <OperatorGate>
      <ItemInfluenceMapContent itemId={id} />
    </OperatorGate>
  )
}

async function ItemInfluenceMapContent({ itemId }: { itemId: string }) {
  const data = await getItemInfluenceMapData(itemId)
  if (!data) notFound()

  const { item, votes, contributions, behested_payments, related_items } = data

  // Build vote result narrative
  const ayes = votes.filter(v => v.vote_choice.toLowerCase() === 'aye')
  const nays = votes.filter(v => v.vote_choice.toLowerCase() === 'nay')
  const hasSplitVote = nays.length > 0

  const voteNarrative = votes.length > 0
    ? hasSplitVote
      ? `Council voted ${ayes.length}–${nays.length} to ${votes[0].motion_result?.toLowerCase() ?? 'decide on'} this item.`
      : `Council voted unanimously (${ayes.length}–0) to ${votes[0].motion_result?.toLowerCase() ?? 'approve'} this item.`
    : null

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <RecordVisit
        type="agenda_item"
        id={itemId}
        title={item.summary_headline ?? item.title}
        url={`/influence/item/${itemId}`}
      />
      {/* 1. Navigation */}
      <nav className="mb-6">
        <Link
          href={`/meetings/${item.meeting_id}`}
          className="text-sm text-civic-navy-light hover:text-civic-navy"
        >
          ← Back to {formatDate(item.meeting_date)}
        </Link>
        <div className="text-xs text-slate-400 mt-1">
          <Link href="/" className="hover:underline">Home</Link>
          {' › '}
          <Link href="/influence" className="hover:underline">Influence Map</Link>
          {' › '}
          <Link href={`/meetings/${item.meeting_id}`} className="hover:underline">
            {formatShortDate(item.meeting_date)}
          </Link>
          {' › '}
          <span className="text-slate-600">Campaign Finance Context</span>
        </div>
      </nav>

      {/* 2. Item Identity */}
      <header className="mb-8">
        <div className="flex items-center gap-2 mb-2">
          <EntityTypeIndicator entityType="agenda_item" showLabel size="md" />
          {item.category && <CategoryBadge category={item.category} />}
        </div>
        <h1 className="text-3xl font-bold text-civic-navy leading-snug">
          {item.summary_headline ?? item.title}
        </h1>
        {item.plain_language_summary && (
          <div className="bg-slate-50 border border-slate-200 rounded-md p-4 mt-4">
            <p className="text-base text-slate-700 leading-relaxed">
              {item.plain_language_summary}
            </p>
            <p className="text-xs text-slate-400 mt-2">
              AI-generated summary · Source: official agenda documents
            </p>
          </div>
        )}
        {/* Official agenda text — collapsed by default since the headline + summary are clearer */}
        {(item.title || item.description) && item.summary_headline && (
          <ExpandableOfficialText title={item.title} description={item.description} />
        )}
        <div className="mt-3">
          <SourceBadge source="Official City Council Minutes" tier={1} />
        </div>
      </header>

      {/* 3. The Decision */}
      {votes.length > 0 && (
        <section className="mb-8">
          <h2 className="text-xl font-semibold text-civic-navy mb-3">The Decision</h2>
          {voteNarrative && (
            <p className="text-base text-slate-700 mb-4">{voteNarrative}</p>
          )}
          <div className="flex flex-wrap gap-2">
            {votes.map(v => (
              <Link
                key={v.official_id}
                href={`/council/${v.official_slug}`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm transition-colors hover:bg-slate-50"
              >
                <EntityTypeIndicator entityType="official" />
                <span className="font-medium">{v.official_name}</span>
                <span className={`font-bold ${
                  v.vote_choice.toLowerCase() === 'aye' ? 'text-vote-aye' :
                  v.vote_choice.toLowerCase() === 'nay' ? 'text-vote-nay' :
                  'text-vote-abstain'
                }`}>
                  {v.vote_choice}
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* 4. Campaign Finance Context */}
      {contributions.length > 0 && (
        <section className="mb-8">
          <h2 className="text-xl font-semibold text-civic-navy mb-1">
            Campaign Finance Context ({contributions.length} {contributions.length === 1 ? 'record' : 'records'})
          </h2>
          <CampaignFinanceDisclaimer />
          <div>
            {contributions.map((n, i) => (
              <ContributionNarrative key={`${n.official_id}-${n.donor_name}-${i}`} narrative={n} />
            ))}
          </div>
          <ConfidenceExplanation />
        </section>
      )}

      {/* 5. Behested Payment Context */}
      {behested_payments.length > 0 && (
        <section className="mb-8">
          <h2 className="text-xl font-semibold text-civic-navy mb-1">
            Behested Payment Context ({behested_payments.length} {behested_payments.length === 1 ? 'record' : 'records'})
          </h2>
          <BehstedPaymentDisclaimer />
          <div>
            {behested_payments.map(p => (
              <BehstedPaymentNarrative key={p.id} payment={p} />
            ))}
          </div>
        </section>
      )}

      {/* 6. Related Decisions */}
      {related_items.length > 0 && (
        <section className="mb-8">
          <h2 className="text-xl font-semibold text-civic-navy mb-3">
            Related Decisions ({related_items.length})
          </h2>
          <p className="text-sm text-slate-500 mb-3">
            Most controversial items involving the same officials in the last 4 years.
          </p>
          <div className="space-y-2">
            {related_items.map(ri => (
              <Link
                key={ri.id}
                href={`/influence/item/${ri.id}`}
                className="block bg-white border border-slate-200 rounded-lg p-3 hover:bg-slate-50 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-slate-900 truncate">
                        {ri.summary_headline ?? ri.title}
                      </p>
                      {ri.has_split_vote && (
                        <span className="shrink-0 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-civic-navy border border-slate-300">
                          Split
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-1 text-xs text-slate-500">
                      <span>{formatShortDate(ri.meeting_date)}</span>
                      {ri.category && (
                        <>
                          <span>·</span>
                          <span>{ri.category.replace(/_/g, ' ')}</span>
                        </>
                      )}
                      <span>·</span>
                      <span>{ri.flag_count} {ri.flag_count === 1 ? 'record' : 'records'}</span>
                    </div>
                  </div>
                  <span className="text-slate-400 text-sm ml-2">→</span>
                </div>
              </Link>
            ))}
          </div>
          {/* Link to see all flagged items from the same meeting */}
          <div className="mt-3 text-center">
            <Link
              href={`/meetings/${item.meeting_id}`}
              className="text-xs text-civic-navy hover:underline"
            >
              View all items from this meeting →
            </Link>
          </div>
        </section>
      )}

      {/* 7. About This Data */}
      <section className="border-t border-slate-200 pt-6 mt-8">
        <h2 className="text-sm font-semibold text-slate-500 mb-2">About This Data</h2>
        <p className="text-sm text-slate-500 leading-relaxed">
          This page compiles publicly available campaign finance records from official
          sources. Data freshness and methodology details are available on the{' '}
          <Link href="/influence/methodology" className="text-civic-navy hover:underline">
            methodology page
          </Link>.
        </p>
        {data.extracted_at && (
          <p className="text-xs text-slate-400 mt-1">
            Last extracted: {new Date(data.extracted_at).toLocaleDateString('en-US')}
          </p>
        )}
      </section>

      {/* Empty state */}
      {contributions.length === 0 && behested_payments.length === 0 && (
        <div className="bg-slate-50 border border-slate-200 rounded-lg p-6 text-center">
          <p className="text-base text-slate-600">
            No campaign finance records were identified for this agenda item.
          </p>
          <p className="text-sm text-slate-500 mt-2">
            This may mean no matching records exist, or that entity matching
            did not identify relevant connections at the published confidence threshold.
          </p>
        </div>
      )}
    </div>
  )
}
