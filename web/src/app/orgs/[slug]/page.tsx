/**
 * Public union/company profile.
 *
 * Uses the same sentence-first profile grammar as political committees:
 * orientation, one filing-based summary, then sortable receipt detail.
 */

import { notFound } from 'next/navigation'
import type { Metadata } from 'next'
import type { ReactNode } from 'react'
import {
  getOrgBySlug,
  getOrgOutgoing,
  getOrgIndependentExpenditures,
} from '@/lib/queries'
import CampaignEntityFinancialDetails from '@/components/CampaignEntityFinancialDetails'
import CampaignEntityProfile from '@/components/CampaignEntityProfile'

interface PageProps {
  params: Promise<{ slug: string }>
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params
  const org = await getOrgBySlug(slug)
  if (!org) return { title: 'Organization not found | Richmond Commons' }
  const label = org.entity_type === 'union' ? 'Union' : 'Company'
  return {
    title: `${org.display_name}: ${label} | Richmond Commons`,
    description: `${org.display_name} has contributed $${org.total_contributed.toLocaleString('en-US', { maximumFractionDigits: 0 })} to Richmond political campaigns. Tracked campaign-finance filings.`,
  }
}

export default async function OrgProfilePage({ params }: PageProps) {
  const { slug } = await params
  const org = await getOrgBySlug(slug)
  if (!org) notFound()

  const [outgoing, independentExpenditures] = await Promise.all([
    getOrgOutgoing(org.donor_ids),
    getOrgIndependentExpenditures(org.display_name),
  ])

  const display = org.display_name
  const isUnion = org.entity_type === 'union'
  const typeLabel = isUnion ? 'Union' : 'Company'

  return (
    <CampaignEntityProfile
      backHref={isUnion ? '/unions' : '/corporations'}
      backLabel={isUnion ? 'All unions' : 'All companies'}
      name={display}
      typeLabel={typeLabel}
      sponsorDisclosure={org.sponsor_disclosure}
      summary={renderLede(org, display, outgoing, independentExpenditures)}
      sourceNote={
        <>
          Organization type is auto-generated from filing names and public
          records. Treat the label as a filing-based classification, not a
          statement about the organization&apos;s goals.
        </>
      }
    >
      <CampaignEntityFinancialDetails
        outgoing={outgoing}
        independentExpenditures={independentExpenditures}
        entityDisplay={display}
        entityNoun="organization"
        entityUrlMap={null}
      />
    </CampaignEntityProfile>
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
