/**
 * DonationsUnderReview — placeholder shown to public visitors in place
 * of campaign-contribution data while the operator validates accuracy.
 *
 * Background (2026-04-26): Leisa Johnson's first-reader feedback flagged
 * Claudia Jimenez's 2024 contributions as inaccurate. Until the data
 * across all council members and candidates is validated against
 * NetFile + CAL-ACCESS sources, donor data is operator-only.
 *
 * Used as the `fallback` of `<OperatorGate>` wraps around DonorTable,
 * ComparativeContext, DonorSection, and donation totals on candidate
 * cards. When the operator removes the gate, this component is
 * unreferenced and can be deleted.
 */
export default function DonationsUnderReview({
  context,
}: {
  /** Optional context (e.g., "for this candidate", "for this councilmember") */
  context?: string
}) {
  const target = context ? ` ${context}` : ''
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
      <p className="text-sm font-medium text-slate-700">
        Campaign contributions{target} are temporarily hidden.
      </p>
      <p className="mt-1 text-sm text-slate-500">
        We&rsquo;re reviewing the accuracy of our campaign-finance data
        against NetFile and CAL-ACCESS records. The display will return
        once we&rsquo;ve verified the underlying ingestion. In the meantime,
        the public records remain available directly:{' '}
        <a
          href="https://public.netfile.com/pub2/?AID=RICH"
          target="_blank"
          rel="noopener noreferrer"
          className="text-civic-navy underline hover:text-civic-amber"
        >
          NetFile (Richmond)
        </a>
        {' · '}
        <a
          href="https://campaignfinance.cdn.sos.ca.gov/"
          target="_blank"
          rel="noopener noreferrer"
          className="text-civic-navy underline hover:text-civic-amber"
        >
          CAL-ACCESS (state)
        </a>
        .
      </p>
    </div>
  )
}
