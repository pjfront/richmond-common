import type { BehstedPaymentNarrativeData } from '@/lib/types'

interface BehstedPaymentNarrativeProps {
  payment: BehstedPaymentNarrativeData
}

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount)
}

/**
 * BehstedPaymentNarrative — S14 C1
 *
 * Renders a behested payment record as a plain-language sentence.
 * Uses a distinct template from campaign contributions because the
 * financial relationship is structurally different: money flows from
 * payor → payee at the official's request, not to the official.
 *
 * Lead with the request relationship, then the vote.
 */
export default function BehstedPaymentNarrative({ payment }: BehstedPaymentNarrativeProps) {
  const p = payment
  const amountLabel = p.amount ? formatCurrency(p.amount) : 'an undisclosed amount'
  const dateLabel = p.payment_date
    ? new Date(p.payment_date + 'T00:00:00').toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      })
    : 'an undisclosed date'

  return (
    <div className="bg-white border border-slate-200 rounded-lg p-4 mb-3">
      <p className="text-sm text-slate-700 leading-relaxed">
        According to FPPC Form 803 filings, {p.official_name} requested
        that {p.payor_name} make a {amountLabel} payment to {p.payee_name}
        {p.payee_description && <span> ({p.payee_description})</span>}
        {' '}on {dateLabel}.
      </p>

      {p.is_also_contributor && (
        <p className="text-sm text-slate-600 leading-relaxed mt-1.5">
          {p.payor_name} is also a campaign contributor to {p.official_name}
          {p.contributor_total && ` (${formatCurrency(p.contributor_total)} total)`}.
        </p>
      )}

      {/* Meta */}
      <div className="flex flex-wrap items-center gap-2 mt-3 text-xs text-slate-500">
        <span>Tier 1 (FPPC Form 803)</span>
        {p.filing_date && (
          <>
            <span>·</span>
            <span>Filed {p.filing_date}</span>
          </>
        )}
        {p.source_url && (
          <>
            <span>·</span>
            <a
              href={p.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-civic-navy hover:underline"
            >
              View filing
            </a>
          </>
        )}
      </div>

      {/* Per-connection disclaimer */}
      <p className="text-xs text-slate-400 italic leading-relaxed mt-2">
        This information comes from FPPC Form 803 filings, which are official
        public records. A behested payment means the official requested that
        someone make a payment to a third party. It does not mean the official
        received money or that the payment influenced any government decision.
      </p>
    </div>
  )
}
