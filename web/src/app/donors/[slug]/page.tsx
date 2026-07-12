/**
 * Individual donor profile page — S28.6, Graduated tier.
 *
 * Follows the org profile pattern (S28.3) simplified for individuals:
 *   - Hero with initials, name, employer/occupation
 *   - Lede narrative (D6: short sentences with inline numbers)
 *   - Cycle bars timeline (per-cycle giving)
 *   - Giving table (contributions FROM this donor)
 *
 * Individuals don't file independent expenditures, so that section is omitted.
 */

import { notFound } from 'next/navigation'
import Link from 'next/link'
import type { Metadata } from 'next'
import type { ReactNode } from 'react'
import {
  getDonorBySlug,
  getDonorOutgoing,
  getDonorCycleBars,
} from '@/lib/queries'
import DonorProfileClient from './DonorProfileClient'

interface PageProps {
  params: Promise<{ slug: string }>
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params
  const donor = await getDonorBySlug(slug)
  if (!donor) return { title: 'Donor not found | Richmond Commons' }
  return {
    title: `${donor.display_name}: Individual Donor | Richmond Commons`,
    description: `${donor.display_name} has contributed $${donor.total_contributed.toLocaleString('en-US', { maximumFractionDigits: 0 })} to Richmond political campaigns. Tracked campaign-finance filings.`,
  }
}

export default async function DonorProfilePage({ params }: PageProps) {
  const { slug } = await params
  const donor = await getDonorBySlug(slug)
  if (!donor) notFound()

  const [outgoing, cycleBars] = await Promise.all([
    getDonorOutgoing(donor.donor_id),
    getDonorCycleBars(donor.donor_id),
  ])

  const display = donor.display_name
  const initials = display
    .split(/\s+/)
    .filter((w) => /^[A-Z]/i.test(w ?? ''))
    .slice(0, 2)
    .join('')
    .toUpperCase() || 'DO'

  return (
    <article className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <Link
        href="/donors"
        className="inline-flex items-center gap-1 text-sm text-civic-navy/60 hover:text-civic-navy transition-colors"
      >
        <span aria-hidden="true">&larr;</span> All individual donors
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
          <div className="flex flex-wrap items-center gap-2 mt-2">
            <span className="px-2.5 py-0.5 text-[11px] font-semibold bg-civic-navy/10 text-civic-navy rounded-full uppercase tracking-wide">
              Individual Donor
            </span>
          </div>
          {(donor.employer || donor.occupation) && (
            <p className="text-sm text-slate-600 mt-2">
              {[donor.employer, donor.occupation].filter(Boolean).join(' · ')}
            </p>
          )}
        </div>
      </header>

      {/* Lede narrative */}
      <div className="border-l-4 border-civic-navy bg-civic-navy/[0.02] rounded-r-lg p-5 sm:p-6 mb-6">
        <p className="text-[15px] text-slate-700 leading-[1.8]">
          {renderLede(donor, display, outgoing)}
        </p>
      </div>

      {/* Temporal + receipt layers (client component for interactivity) */}
      <DonorProfileClient
        outgoing={outgoing}
        cycleBars={cycleBars}
        donorDisplay={display}
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
          (California Secretary of State, Tier 1 source).
        </p>
        <p className="text-xs text-slate-400">
          Individual donor pages show only donors whose aggregate giving across
          all tracked cycles exceeds $5,000. All data is public record.
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
  donor: {
    total_contributed: number
    recipient_count: number
    employer: string | null
    earliest_contribution_date: string | null
    latest_contribution_date: string | null
  },
  display: string,
  outgoing: Array<{
    amount: number
    recipient_committee_name: string
    recipient_candidate_name: string | null
  }>,
): ReactNode {
  if (donor.total_contributed <= 0) {
    return <>No contribution data tracked for {display}.</>
  }
  const span =
    donor.earliest_contribution_date && donor.latest_contribution_date
      ? ` between ${fmtDate(donor.earliest_contribution_date)} and ${fmtDate(donor.latest_contribution_date)}`
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

  // Top recipient: how much went to the largest recipient?
  const topAmount = top.length > 0 ? top[0][1] : 0
  const concentration =
    donor.total_contributed > 0
      ? Math.round((topAmount / donor.total_contributed) * 100)
      : 0

  return (
    <>
      <strong>{display}</strong>
      {donor.employer ? (
        <>
          , {donor.employer.startsWith('Self') || donor.employer.startsWith('Retired')
            ? ' currently reporting as '
            : ' employed by '}
          <strong>{donor.employer}</strong>,
        </>
      ) : (
        ','
      )}{' '}
      has contributed{' '}
      <strong>${fmt(donor.total_contributed)}</strong>
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
      .{' '}
      {concentration >= 70 && top.length > 0 ? (
        <>
          Giving is heavily concentrated: {concentration}% of all contributions
          went to <strong>{top[0][0]}</strong>.
        </>
      ) : concentration >= 40 && top.length > 0 ? (
        <>
          The largest recipient, <strong>{top[0][0]}</strong>, received{' '}
          {concentration}% of all giving.
        </>
      ) : donor.recipient_count > 0 ? (
        <>
          Giving is spread across{' '}
          <strong>{donor.recipient_count}</strong> recipient
          {donor.recipient_count === 1 ? '' : 's'}.
        </>
      ) : null}
    </>
  )
}
