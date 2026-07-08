/**
 * PAC profile page.
 *
 * Three-layer grammar per docs/design/PAC-MATRIX-DESIGN.md:
 *   - Hero (initials, display name, sponsor disclosure)
 *   - Lede narrative (D6: short sentences with inline numbers)
 *   - EXPLORE: PACFlowMatrix — donors x candidates conduit grid
 *     (Phase 1: read-only. Phase 2 will add selection state and
 *     per-cell drill into the detail tables below.)
 *   - RECEIPT: existing donor + outgoing detail tables
 *
 * The middle "temporal" layer (CycleBarsTimeline.tsx, the cycle mirror
 * named in docs/design/INTERACTIVE-DATA-VIZ.md) is Phase 3.
 *
 * Independent expenditures (CAL-ACCESS EXPN_CD) are NOW dedup-clean as
 * of migration 102 (D49 shipped, 122K -> 2.2K rows). An IE detail
 * section will land in Phase 2 alongside the matrix selection state.
 *
 * Publication tier: Public. Graduated from operator-only 2026-07-06 (S28.4).
 */

import { notFound } from 'next/navigation'
import Link from 'next/link'
import type { Metadata } from 'next'
import type { ReactNode } from 'react'
import {
  getPACBySlug,
  getPACList,
  getPACContributions,
  getPACOutgoing,
  getPACFlowMatrix,
  getPACIndependentExpenditures,
} from '@/lib/queries'
import PACProfileDashboard from './PACProfileDashboard'

interface PageProps {
  params: Promise<{ slug: string }>
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params
  const pac = await getPACBySlug(slug)
  if (!pac) return { title: 'Committee not found | Richmond Commons' }
  const display = displayName(pac.name)
  return {
    title: `${display}: Political Committee | Richmond Commons`,
    description: pac.sponsor_disclosure
      ? `${display} (${pac.sponsor_disclosure}). Public campaign-finance filings.`
      : `${display}: Richmond political committee filings.`,
  }
}

export default async function PACProfilePage({ params }: PageProps) {
  const { slug } = await params
  const pac = await getPACBySlug(slug)
  if (!pac) notFound()

  const [pacList, contributions, outgoing, flowMatrix, independentExpenditures] = await Promise.all([
    getPACList(),
    getPACContributions(pac.member_ids),
    getPACOutgoing(pac.name),
    getPACFlowMatrix(pac.member_ids, pac.name),
    getPACIndependentExpenditures(pac.name),
  ])

  // Build name→URL map for cross-linking (S28.5). Maps both the
  // full registered name and the display name (before comma) since
  // donor records use either form.
  const pacUrlMap = new Map<string, string>()
  for (const p of pacList) {
    const key = p.name.toLowerCase().trim()
    pacUrlMap.set(key, `/pac/${p.slug}`)
    const display = p.name.split(',')[0].trim().toLowerCase()
    if (display !== key) pacUrlMap.set(display, `/pac/${p.slug}`)
  }

  const display = displayName(pac.name)
  const initials = display
    .split(/\s+/)
    .map((w) => w[0])
    .filter((c) => /[A-Z]/i.test(c ?? ''))
    .slice(0, 2)
    .join('')
    .toUpperCase()

  return (
    <article className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Link
          href="/pac"
          className="inline-flex items-center gap-1 text-sm text-civic-navy/60 hover:text-civic-navy transition-colors"
        >
          <span aria-hidden="true">&larr;</span> All political committees
        </Link>

        {/* Hero */}
        <header className="mt-5 mb-8 flex items-start gap-5">
          <div className="w-16 h-16 rounded-full bg-gradient-to-br from-civic-amber to-civic-amber-light text-white text-xl font-bold flex items-center justify-center shrink-0 mt-0.5">
            {initials || 'PC'}
          </div>
          <div className="min-w-0">
            <h1 className="text-3xl sm:text-4xl font-bold text-civic-navy tracking-tight">
              {display}
            </h1>
            {display !== pac.name && (
              <p className="text-sm text-slate-500 mt-1.5 leading-snug">
                Filed as: {pac.name}
              </p>
            )}
            <div className="flex flex-wrap items-center gap-2 mt-2">
              <span className="px-2.5 py-0.5 text-[11px] font-semibold bg-civic-amber/10 text-civic-amber rounded-full uppercase tracking-wide">
                Political committee
              </span>
              {pac.filer_id && pac.filer_id !== 'Pending' && (
                <span className="text-[11px] text-slate-400 tabular-nums">
                  Filer ID {pac.filer_id}
                </span>
              )}
            </div>
            {pac.sponsor_disclosure && (
              <p className="text-sm text-civic-amber mt-3 font-medium">
                {pac.sponsor_disclosure}
              </p>
            )}
          </div>
        </header>

        {/* Lede narrative */}
        <div className="border-l-4 border-civic-navy bg-civic-navy/[0.02] rounded-r-lg p-5 sm:p-6 mb-6">
          <p className="text-[15px] text-slate-700 leading-[1.8]">
            {renderLede(pac, display, outgoing.length, independentExpenditures)}
          </p>
        </div>

        {/* Unified template: every PAC gets cycle-bars timeline +
            receipt tables. The matrix grid above only renders when
            this PAC's outflows trace to candidates. */}
        <PACProfileDashboard
          matrix={flowMatrix}
          contributions={contributions}
          outgoing={outgoing}
          independentExpenditures={independentExpenditures}
          pacDisplay={display}
          pacUrlMap={pacUrlMap}
        />

        {/* Footer */}
        <footer className="mt-12 pt-6 border-t border-slate-100 space-y-2">
          <p className="text-xs text-slate-400 leading-relaxed">
            Contribution data from{' '}
            <a
              href="https://public.netfile.com/pub2/?AID=RICH"
              target="_blank"
              rel="noopener noreferrer"
              className="text-civic-navy hover:underline"
            >
              NetFile
            </a>{' '}
            (City of Richmond e-filing system, Tier 1 source) and CAL-ACCESS
            (California Secretary of State, Tier 1 source). Sponsor
            disclosures are inferred from the committee name as filed; the
            Chevron disclosure for Coalition for Richmond&apos;s Future
            follows the project source-credibility-tier rule.
          </p>
          <p className="text-xs text-slate-400">
            Auto-generated from public records &middot; Updated within ~15
            minutes of any new filing
          </p>
        </footer>
    </article>
  )
}

// ─── Helpers ───────────────────────────────────────────────────────────

/** Trim the verbose registered name down to a display label.
 *  "Foo Committee, sponsored by Bar" → "Foo Committee". */
function displayName(name: string): string {
  const beforeComma = name.split(',')[0].trim()
  return beforeComma.length >= 6 ? beforeComma : name
}

function fmt(n: number): string {
  return n.toLocaleString('en-US', { maximumFractionDigits: 0 })
}

function fmtDate(iso: string): string {
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', {
    month: 'short',
    year: 'numeric',
  })
}

// ─── Narrative builders ────────────────────────────────────────────────

function renderLede(
  pac: { total_raised: number; donor_count: number; earliest_contribution_date: string | null; latest_contribution_date: string | null },
  display: string,
  outgoingCount: number,
  ieRows: Array<{ amount: number; candidate_name: string | null; support_or_oppose: string | null }>,
): ReactNode {
  if (pac.total_raised <= 0) {
    return <>No contribution data tracked for {display}.</>
  }
  const span =
    pac.earliest_contribution_date && pac.latest_contribution_date
      ? ` between ${fmtDate(pac.earliest_contribution_date)} and ${fmtDate(pac.latest_contribution_date)}`
      : ''
  const ieTotal = ieRows.reduce((s, r) => s + r.amount, 0)

  // Aggregate support/oppose by candidate
  const supportCandidates = new Map<string, number>()
  const opposeCandidates = new Map<string, number>()
  for (const r of ieRows) {
    if (!r.candidate_name) continue
    const map = r.support_or_oppose === 'O' ? opposeCandidates : supportCandidates
    map.set(r.candidate_name, (map.get(r.candidate_name) ?? 0) + r.amount)
  }

  return (
    <>
      <strong>{display}</strong> has raised{' '}
      <strong>${fmt(pac.total_raised)}</strong> from{' '}
      <strong>{fmt(pac.donor_count)}</strong> donor
      {pac.donor_count === 1 ? '' : 's'}
      {span}.
      {ieTotal > 0 && (
        <>
          {' '}It spent <strong>${fmt(ieTotal)}</strong> on ads and mailers
          {supportCandidates.size > 0 && (
            <>
              {' '}supporting{' '}
              {Array.from(supportCandidates.entries())
                .sort((a, b) => b[1] - a[1])
                .map(([name, amt], i, arr) => (
                  <span key={name}>
                    {i > 0 && i === arr.length - 1 ? ' and ' : i > 0 ? ', ' : ''}
                    <strong>{name}</strong> (${fmt(amt)})
                  </span>
                ))}
            </>
          )}
          {opposeCandidates.size > 0 && (
            <>
              {supportCandidates.size > 0 ? ', and ' : ' '}opposing{' '}
              {Array.from(opposeCandidates.entries())
                .sort((a, b) => b[1] - a[1])
                .map(([name, amt], i, arr) => (
                  <span key={name}>
                    {i > 0 && i === arr.length - 1 ? ' and ' : i > 0 ? ', ' : ''}
                    <strong>{name}</strong> (${fmt(amt)})
                  </span>
                ))}
            </>
          )}
          .
        </>
      )}
      {outgoingCount > 0 && (
        <>
          {' '}It shows up as a donor on{' '}
          <strong>{outgoingCount}</strong> filing
          {outgoingCount === 1 ? '' : 's'} from other Richmond committees.
        </>
      )}
    </>
  )
}

