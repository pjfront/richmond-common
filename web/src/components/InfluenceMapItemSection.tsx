/**
 * Operator-gated influence-map content for a single agenda item.
 *
 * Folded into the canonical agenda-item page (`/meetings/[id]/items/[itemNumber]`)
 * by Phase 2.6 of the re-architecture. Previously rendered as a standalone page
 * at `/influence/item/[id]`, which now permanently redirects to the canonical URL.
 *
 * Renders the unique content that lived only on the influence map page:
 *   - Campaign-finance contribution narratives
 *   - Behested payment narratives
 *   - Related decisions (most controversial items involving the same officials)
 *
 * The canonical page already shows votes/comments/related-topic items, so those
 * pieces are intentionally NOT duplicated here.
 */
import Link from 'next/link'
import { agendaItemPath } from '@/lib/format'
import type { ItemInfluenceMapData } from '@/lib/types'
import ContributionNarrative from '@/components/ContributionNarrative'
import BehstedPaymentNarrative from '@/components/BehstedPaymentNarrative'
import {
  CampaignFinanceDisclaimer,
  BehstedPaymentDisclaimer,
  ConfidenceExplanation,
} from '@/components/InfluenceDisclaimer'

interface Props {
  data: ItemInfluenceMapData
  meetingId: string
}

function formatShortDate(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

export default function InfluenceMapItemSection({ data, meetingId }: Props) {
  const { contributions, behested_payments, related_items, extracted_at } = data

  const hasAny = contributions.length > 0 || behested_payments.length > 0 || related_items.length > 0
  if (!hasAny) return null

  return (
    <div className="mb-8 pt-6 border-t border-slate-200">
      <h2 className="text-xs font-semibold text-civic-amber uppercase tracking-widest mb-4">
        Operator: campaign-finance context
      </h2>

      {contributions.length > 0 && (
        <section className="mb-8">
          <h3 className="text-lg font-semibold text-civic-navy mb-1">
            Campaign Finance Context ({contributions.length} {contributions.length === 1 ? 'record' : 'records'})
          </h3>
          <CampaignFinanceDisclaimer />
          <div>
            {contributions.map((n, i) => (
              <ContributionNarrative key={`${n.official_id}-${n.donor_name}-${i}`} narrative={n} />
            ))}
          </div>
          <ConfidenceExplanation />
        </section>
      )}

      {behested_payments.length > 0 && (
        <section className="mb-8">
          <h3 className="text-lg font-semibold text-civic-navy mb-1">
            Behested Payment Context ({behested_payments.length}{' '}
            {behested_payments.length === 1 ? 'record' : 'records'})
          </h3>
          <BehstedPaymentDisclaimer />
          <div>
            {behested_payments.map((p) => (
              <BehstedPaymentNarrative key={p.id} payment={p} />
            ))}
          </div>
        </section>
      )}

      {related_items.length > 0 && (
        <section className="mb-8">
          <h3 className="text-lg font-semibold text-civic-navy mb-3">
            Related Decisions ({related_items.length})
          </h3>
          <p className="text-sm text-slate-500 mb-3">
            Most controversial items involving the same officials in the last 4 years.
          </p>
          <div className="space-y-2">
            {related_items.map((ri) => (
              <Link
                key={ri.id}
                href={agendaItemPath(ri.meeting_id, ri.item_number)}
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
                          <span>&middot;</span>
                          <span>{ri.category.replace(/_/g, ' ')}</span>
                        </>
                      )}
                      <span>&middot;</span>
                      <span>
                        {ri.flag_count} {ri.flag_count === 1 ? 'record' : 'records'}
                      </span>
                    </div>
                  </div>
                  <span className="text-slate-400 text-sm ml-2">&rarr;</span>
                </div>
              </Link>
            ))}
          </div>
          <div className="mt-3 text-center">
            <Link
              href={`/meetings/${meetingId}`}
              className="text-xs text-civic-navy hover:underline"
            >
              View all items from this meeting &rarr;
            </Link>
          </div>
        </section>
      )}

      <p className="text-xs text-slate-400 leading-relaxed">
        Auto-generated from public campaign-finance records. Methodology details on the{' '}
        <Link href="/influence/methodology" className="text-civic-navy hover:underline">
          methodology page
        </Link>
        .
        {extracted_at && (
          <>
            {' '}Last extracted: {new Date(extracted_at).toLocaleDateString('en-US')}.
          </>
        )}
      </p>
    </div>
  )
}
