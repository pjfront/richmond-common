/**
 * Organization profile page — S28.3, Graduated tier.
 *
 * Follows the PAC V2 grammar (hero → lede → cycle bars → receipt tables)
 * simplified for orgs, which only have one direction: money OUT (org → committees).
 *
 * Each profile shows:
 *   - Hero with display name, type badge, mandatory disclosure
 *   - Lede narrative (D6: short sentences with inline numbers)
 *   - Cycle bars timeline (per-cycle giving)
 *   - Giving table (contributions FROM this org)
 *   - Independent expenditures (when data exists)
 */

import { notFound } from 'next/navigation'
import Link from 'next/link'
import type { Metadata } from 'next'
import type { ReactNode } from 'react'
import {
  getOrgBySlug,
  getOrgOutgoing,
  getOrgCycleBars,
  getOrgIndependentExpenditures,
} from '@/lib/queries'
import OrgProfileClient from './OrgProfileClient'

interface PageProps {
  params: Promise<{ slug: string }>
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params
  const org = await getOrgBySlug(slug)
  if (!org) return { title: 'Organization not found' }
  const label =
    org.entity_type === 'union' ? 'Union' : org.entity_type === 'corporation' ? 'Corporation' : 'Organization'
  return {
    title: `${org.display_name}: ${label}`,
    description: `${org.display_name} has contributed $${org.total_contributed.toLocaleString('en-US', { maximumFractionDigits: 0 })} to Richmond political campaigns. Tracked campaign-finance filings.`,
  }
}

export default async function OrgProfilePage({ params }: PageProps) {
  const { slug } = await params
  const org = await getOrgBySlug(slug)
  if (!org) notFound()

  const [outgoing, cycleBars, independentExpenditures] = await Promise.all([
    getOrgOutgoing(org.donor_ids),
    getOrgCycleBars(org.donor_ids),
    getOrgIndependentExpenditures(org.display_name),
  ])

  const display = org.display_name
  const initials = display
    .split(/\s+/)
    .filter((w) => /^[A-Z]/i.test(w ?? ''))
    .slice(0, 2)
    .join('')
    .toUpperCase() || 'OR'

  const typeLabel =
    org.entity_type === 'union' ? 'Union' : org.entity_type === 'corporation' ? 'Corporation' : org.entity_type

  return (
    <article className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Link
          href="/orgs"
          className="inline-flex items-center gap-1 text-sm text-civic-navy/60 hover:text-civic-navy transition-colors"
        >
          <span aria-hidden="true">&larr;</span> All organizations
        </Link>

        {/* Hero */}
        <header className="mt-5 mb-8 flex items-start gap-5">
          <div className="w-16 h-16 rounded-full bg-gradient-to-br from-civic-navy to-civic-navy-light text-white text-xl font-bold flex items-center justify-center shrink-0 mt-0.5">
            {initials}
          </div>
          <div className="min-w-0">
            <h1 className="text-3xl sm:text-4xl font-bold text-civic-navy tracking-tight">
              {display}
            </h1>
            {display !== org.display_name && (
              <p className="text-sm text-slate-500 mt-1.5 leading-snug">
                Filed as: {org.display_name}
              </p>
            )}
            <div className="flex flex-wrap items-center gap-2 mt-2">
              <span className="px-2.5 py-0.5 text-[11px] font-semibold bg-civic-amber/10 text-civic-amber rounded-full uppercase tracking-wide">
                {typeLabel}
              </span>
            </div>
            {org.sponsor_disclosure && (
              <p className="text-sm text-civic-amber mt-3 font-medium">
                {org.sponsor_disclosure}
              </p>
            )}
          </div>
        </header>

        {/* Lede narrative */}
        <div className="border-l-4 border-civic-navy bg-civic-navy/[0.02] rounded-r-lg p-5 sm:p-6 mb-6">
          <p className="text-[15px] text-slate-700 leading-[1.8]">
            {renderLede(org, display, outgoing, independentExpenditures)}
          </p>
        </div>

        {/* Temporal + receipt layers (client component for interactivity) */}
        <OrgProfileClient
          outgoing={outgoing}
          cycleBars={cycleBars}
          independentExpenditures={independentExpenditures}
          orgDisplay={display}
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
            (California Secretary of State, Tier 1 source). Organization
            classification is auto-generated from name patterns and public
            records.
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

function fmt(n: number): string {
  return n.toLocaleString('en-US', { maximumFractionDigits: 0 })
}

function fmtDate(iso: string): string {
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', {
    month: 'short',
    year: 'numeric',
  })
}

// ─── Narrative builder ─────────────────────────────────────────────────

function renderLede(
  org: {
    total_contributed: number
    recipient_count: number
    earliest_contribution_date: string | null
    latest_contribution_date: string | null
  },
  display: string,
  outgoing: Array<{
    amount: number
    recipient_committee_name: string
    recipient_candidate_name: string | null
  }>,
  ieRows: Array<{ amount: number; candidate_name: string | null; support_or_oppose: string | null }>,
): ReactNode {
  if (org.total_contributed <= 0) {
    return <>No contribution data tracked for {display}.</>
  }
  const span =
    org.earliest_contribution_date && org.latest_contribution_date
      ? ` between ${fmtDate(org.earliest_contribution_date)} and ${fmtDate(org.latest_contribution_date)}`
      : ''

  // Top recipients
  const byCommittee = new Map<string, number>()
  for (const o of outgoing) {
    const key = o.recipient_candidate_name ?? o.recipient_committee_name
    byCommittee.set(key, (byCommittee.get(key) ?? 0) + o.amount)
  }
  const top = Array.from(byCommittee.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)

  const ieTotal = ieRows.reduce((s, r) => s + r.amount, 0)

  // Aggregate support/oppose by candidate for IE spending
  const supportCandidates = new Map<string, number>()
  const opposeCandidates = new Map<string, number>()
  for (const r of ieRows) {
    if (!r.candidate_name) continue
    const map = r.support_or_oppose === 'O' ? opposeCandidates : supportCandidates
    map.set(r.candidate_name, (map.get(r.candidate_name) ?? 0) + r.amount)
  }

  return (
    <>
      <strong>{display}</strong> has contributed{' '}
      <strong>${fmt(org.total_contributed)}</strong>
      {span}
      {top.length > 0 && (
        <>
          , with the largest amounts going to{' '}
          {top.map(([name, amount], i) => (
            <span key={name}>
              {i > 0 && i === top.length - 1 ? ' and ' : i > 0 ? ', ' : ''}
              <strong>{name}</strong> (${fmt(amount)})
            </span>
          ))}
        </>
      )}
      .
      {ieTotal > 0 && (
        <>
          {' '}It also spent <strong>${fmt(ieTotal)}</strong> on ads and mailers
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
    </>
  )
}
