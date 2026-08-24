/**
 * Public political-committee profile.
 *
 * Uses the same sentence-first profile grammar as union and company pages:
 * orientation, one filing-based summary, then sortable receipt detail.
 */

import { notFound } from 'next/navigation'
import type { Metadata } from 'next'
import type { ReactNode } from 'react'
import {
  getPACBySlug,
  getPACList,
  getPACContributions,
  getPACOutgoing,
  getPACIndependentExpenditures,
} from '@/lib/queries'
import CampaignEntityFinancialDetails from '@/components/CampaignEntityFinancialDetails'
import CampaignEntityProfile from '@/components/CampaignEntityProfile'
import type { EntityUrlMap } from '@/components/EntityLink'

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

  const [pacList, contributions, outgoing, independentExpenditures] =
    await Promise.all([
      getPACList(),
      getPACContributions(pac.member_ids),
      getPACOutgoing(pac.name),
      getPACIndependentExpenditures(pac.name),
    ])

  // Build name→URL map for cross-linking (S28.5). Maps both the
  // full registered name and the display name (before comma) since
  // donor records use either form.
  const pacUrlMap: EntityUrlMap = {}
  for (const p of pacList) {
    const key = p.name.toLowerCase().trim()
    pacUrlMap[key] = `/pac/${p.slug}`
    const siblingDisplay = p.name.split(',')[0].trim().toLowerCase()
    if (siblingDisplay !== key) {
      pacUrlMap[siblingDisplay] = `/pac/${p.slug}`
    }
  }

  const display = displayName(pac.name)

  return (
    <CampaignEntityProfile
      backHref="/pac"
      backLabel="All political committees"
      name={display}
      filedName={pac.name}
      typeLabel="Political committee"
      filingId={pac.filer_id}
      sponsorDisclosure={pac.sponsor_disclosure}
      summary={renderLede(
        pac,
        display,
        outgoing.length,
        independentExpenditures,
      )}
      sourceNote={
        <>
          Sponsor descriptions come from the committee name as filed. The
          Chevron disclosure for Coalition for Richmond&apos;s Future follows
          the project&apos;s source-disclosure rule.
        </>
      }
    >
      <CampaignEntityFinancialDetails
        incoming={contributions}
        outgoing={outgoing}
        independentExpenditures={independentExpenditures}
        entityDisplay={display}
        entityNoun="committee"
        entityUrlMap={pacUrlMap}
      />
    </CampaignEntityProfile>
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

