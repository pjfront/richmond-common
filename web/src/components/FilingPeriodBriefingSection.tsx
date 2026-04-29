/**
 * Filing-period briefing — per-candidate sections F1 (totals), F2
 * (geography), F3 (industry/PAC), F4 (self/related-party).
 *
 * Renders one slice of a `filing_period_briefings` row for a single
 * candidate, identified by their `election_candidate_id`. Each section
 * carries its own A/B/C significance tier and ≥0 confidence; the
 * renderer surfaces both inline so the operator can judge readiness
 * before promoting from Graduated to Public.
 *
 * Design rules:
 *  - D1 (provenance fields non-nullable): the briefing row carries
 *    source_url (NetFile portal link via SourceLabel), extracted_at
 *    (provenance.as_of), source_tier (Tier 1 — official records), and
 *    confidence_score (per-section). All four surface in the footer.
 *  - D6 (narrative over numbers): each section is a sentence with
 *    inline dollar amounts, not a chart.
 *  - D2 (low-confidence hidden from summary counts): F3 (0.80) and F4
 *    (0.75) sit below the 0.90 threshold for summary-level surfacing,
 *    so they appear as collapsible "Detail" rows rather than the
 *    primary narrative.
 *
 * The section is operator-only by inheritance — the candidate page is
 * already wrapped in <OperatorGate>. Public graduation per-section
 * happens through the `section_tiers` JSONB once F5–F9 ship and the
 * cross-candidate dashboard reconciles the framing.
 */

import type {
  FilingPeriodBriefing,
  F1Totals,
  F2Geography,
  F3IndustryPac,
  F4SelfRelated,
} from '@/lib/types'
import { BriefingAttribution } from './SourceAttribution'

interface Props {
  briefing: FilingPeriodBriefing
  candidateId: string
  candidateName: string
  /** True when paper filings are known to be incomplete (e.g., Type3 PDFs).
   *  Triggers a "data not final" caveat band above the totals. */
  paperFilingsIncomplete?: boolean
}

export default function FilingPeriodBriefingSection({
  briefing,
  candidateId,
  candidateName,
  paperFilingsIncomplete = false,
}: Props) {
  const f1 = briefing.sections.F1_totals?.per_candidate?.[candidateId]
  const f2 = briefing.sections.F2_geography?.per_candidate?.[candidateId]
  const f3 = briefing.sections.F3_industry_pac?.per_candidate?.[candidateId]
  const f4 = briefing.sections.F4_self_related?.per_candidate?.[candidateId]

  // Defensive: if no F1 row exists for this candidate, skip the whole
  // section. Most likely cause is a candidate-without-committee orphan
  // that the mapping audit (Stream 1) flags.
  if (!f1) return null

  const periodEnd = new Date(briefing.period_end + 'T00:00:00').toLocaleDateString(
    'en-US',
    { month: 'long', day: 'numeric', year: 'numeric' },
  )
  const firstName = candidateName.split(' ')[0]

  return (
    <section className="mb-6">
      <div className="border border-slate-200 rounded-lg p-5 sm:p-6">
        <div className="flex items-baseline justify-between gap-3 mb-3">
          <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-widest">
            Filing-period briefing — {briefing.period_label}
          </h2>
          <span className="text-[11px] text-slate-400 tabular-nums shrink-0">
            closed {periodEnd}
          </span>
        </div>

        {paperFilingsIncomplete && (
          <div className="mb-4 p-3 rounded-md bg-civic-amber/[0.05] border border-civic-amber/20 text-[13px] text-slate-700">
            <strong className="text-civic-amber">Data not final.</strong>{' '}
            Some paper-filed disclosures haven&apos;t been text-extracted yet
            (image-based PDFs require OCR). The totals below cover what was
            successfully extracted as of generation; numbers will reconcile
            upward as paper filings are processed.
          </div>
        )}

        {/* ── F1: totals (Tier A — full-confidence) ─────────────── */}
        <p className="text-[15px] text-slate-700 leading-[1.8]">
          {renderF1Narrative(f1, firstName, briefing.period_label)}
        </p>

        {/* ── F2: geography (Tier A) ─────────────────────────────── */}
        {f2 && f2.total_amount > 0 && (
          <p className="text-[15px] text-slate-700 leading-[1.8] mt-3">
            {renderF2Narrative(f2, firstName)}
          </p>
        )}

        {/* ── F3: industry/PAC (Tier B — confidence 0.80) ────────── */}
        {f3 && (f3.pac_amount > 0 || f3.top_employers.length > 0) && (
          <details className="mt-4 group">
            <summary className="text-[13px] font-medium text-civic-navy/80 cursor-pointer hover:text-civic-navy">
              Industry &amp; PAC concentration
              <span className="ml-2 text-[11px] font-normal text-slate-400">
                Tier B · 80% confidence
              </span>
            </summary>
            <p className="mt-2 text-[15px] text-slate-700 leading-[1.8]">
              {renderF3Narrative(f3, firstName)}
            </p>
          </details>
        )}

        {/* ── F4: self/related-party (Tier B — confidence 0.75) ──── */}
        {f4 &&
          (f4.self_funded_amount > 0 || f4.related_last_name_amount > 0) && (
            <details className="mt-3 group">
              <summary className="text-[13px] font-medium text-civic-navy/80 cursor-pointer hover:text-civic-navy">
                Self-funding &amp; possible family contributions
                <span className="ml-2 text-[11px] font-normal text-slate-400">
                  Tier B · 75% confidence
                </span>
              </summary>
              <p className="mt-2 text-[15px] text-slate-700 leading-[1.8]">
                {renderF4Narrative(f4, firstName, candidateName)}
              </p>
            </details>
          )}

        <p className="text-xs text-slate-400 mt-5 pt-4 border-t border-slate-100 leading-relaxed">
          <BriefingAttribution p={briefing.provenance} />
        </p>
        <p className="text-[11px] text-slate-400 mt-2 leading-relaxed">
          Updated within ~15 minutes of any new filing.{' '}
          <span title="A change-detector polls the NetFile RSS feed every 15 minutes. When a new Form 460 or 497 appears, the pipeline auto-extracts it, reconciles to the form's cover-page Total, and refreshes this page on the next visit (ISR, ~1 hour cache TTL).">
            Pipeline cadence&nbsp;ⓘ
          </span>{' '}
          &middot; Reconciled to Form 460 Line 1 Monetary (the candidate&apos;s own legal filing).
        </p>
      </div>
    </section>
  )
}

// ── Narrative builders (D6: sentences with inline numbers) ────────────

function renderF1Narrative(
  f1: F1Totals,
  firstName: string,
  periodLabel: string,
): React.ReactNode {
  if (f1.total_amount === 0) {
    return (
      <>
        No contributions tracked for {firstName}&apos;s committee in the{' '}
        {periodLabel} filing period.
      </>
    )
  }
  return (
    <>
      In the <strong>{periodLabel}</strong> filing period, {firstName}&apos;s
      committee reported <strong>${fmt(f1.total_amount)}</strong> from{' '}
      <strong>{f1.unique_donors}</strong> unique donor
      {f1.unique_donors === 1 ? '' : 's'}
      {f1.contribution_count !== f1.unique_donors && (
        <> ({f1.contribution_count} contribution{f1.contribution_count === 1 ? '' : 's'} total)</>
      )}
      . The typical gift was <strong>${fmt(f1.average_gift)}</strong>; the
      largest single gift was <strong>${fmt(f1.max_single_gift)}</strong>.
    </>
  )
}

function renderF2Narrative(f2: F2Geography, firstName: string): React.ReactNode {
  const richmondPct = pct(f2.buckets_share.richmond)
  const bayAreaPct = pct(f2.buckets_share.bay_area)
  const oosPct = pct(f2.buckets_share.out_of_state)
  const richmondAmt = f2.buckets_amount.richmond
  const oosAmt = f2.buckets_amount.out_of_state

  // Lead with whichever bucket dominates — Richmond residents care most
  // about whether the money is local. Out-of-state is the contrast.
  if (richmondPct >= 50) {
    return (
      <>
        Of that, <strong>${fmt(richmondAmt)}</strong> ({richmondPct}%) came from{' '}
        <strong>Richmond zip codes</strong>
        {oosPct > 5 && (
          <>; <strong>${fmt(oosAmt)}</strong> ({oosPct}%) came from out of state</>
        )}
        .
      </>
    )
  }
  if (oosPct >= 30) {
    return (
      <>
        <strong>${fmt(oosAmt)}</strong> ({oosPct}%) of {firstName}&apos;s
        contributions came from <strong>out-of-state donors</strong>; only{' '}
        <strong>${fmt(richmondAmt)}</strong> ({richmondPct}%) came from
        Richmond.
      </>
    )
  }
  return (
    <>
      Donor geography: <strong>{richmondPct}% Richmond</strong>,{' '}
      <strong>{bayAreaPct}% rest of Bay Area</strong>,{' '}
      <strong>{pct(f2.buckets_share.california_other)}% California elsewhere</strong>,{' '}
      <strong>{oosPct}% out of state</strong>.
    </>
  )
}

function renderF3Narrative(f3: F3IndustryPac, firstName: string): React.ReactNode {
  const pacPct = pct(f3.pac_share)
  const top = f3.top_employers.slice(0, 3)
  const employersList = top.map((e, i) => (
    <span key={i}>
      {i > 0 && (i === top.length - 1 ? ', and ' : ', ')}
      <strong>{titleCase(e.employer)}</strong> (${fmt(e.amount)})
    </span>
  ))
  return (
    <>
      {f3.pac_amount > 0 ? (
        <>
          PACs and committees contributed <strong>${fmt(f3.pac_amount)}</strong>{' '}
          ({pacPct}% of {firstName}&apos;s total).
        </>
      ) : (
        <>No PAC contributions tracked for this period.</>
      )}
      {top.length > 0 && (
        <>
          {' '}Largest employer aggregations: {employersList}. Note that
          employer matching is string-based until entity resolution lands —
          variants like &quot;Chevron&quot; vs &quot;Chevron Corp&quot;
          appear as separate rows.
        </>
      )}
    </>
  )
}

function renderF4Narrative(
  f4: F4SelfRelated,
  firstName: string,
  fullName: string,
): React.ReactNode {
  const lastName = fullName.trim().split(/\s+/).slice(-1)[0]
  const hasSelf = f4.self_funded_amount > 0
  const hasRelated = f4.related_last_name_amount > 0

  if (!hasSelf && !hasRelated) {
    return <>No self-funding or family-name matches detected.</>
  }
  return (
    <>
      {hasSelf && (
        <>
          {firstName} self-funded <strong>${fmt(f4.self_funded_amount)}</strong>.
        </>
      )}
      {hasSelf && hasRelated && ' '}
      {hasRelated && (
        <>
          {f4.related_last_name_donors.length} donor
          {f4.related_last_name_donors.length === 1 ? '' : 's'} sharing the{' '}
          <strong>{lastName}</strong> surname contributed{' '}
          <strong>${fmt(f4.related_last_name_amount)}</strong>. Surname match
          alone does not establish a family relationship — common surnames
          produce false positives.
        </>
      )}
    </>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────

function fmt(n: number): string {
  return n.toLocaleString('en-US', { maximumFractionDigits: 0 })
}

function pct(share: number): number {
  return Math.round(share * 100)
}

function titleCase(s: string): string {
  return s
    .split(' ')
    .map((w) => (w.length > 0 ? w[0].toUpperCase() + w.slice(1) : w))
    .join(' ')
}
