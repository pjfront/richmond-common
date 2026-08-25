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
  if (!org) return { title: 'Organization not found' }
  const label = org.entity_type === 'union' ? 'Union' : 'Company'
  return {
    title: `${org.display_name}: ${label}`,
    description: `Public campaign records for ${org.display_name}, including available recipient and filing detail.`,
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
  const activities = [
    org.total_contributed > 0 || outgoing.length > 0
      ? 'contributions to committees'
      : null,
    ieRows.length > 0 ? 'independent expenditures' : null,
  ].filter((activity): activity is string => Boolean(activity))

  if (activities.length === 0) {
    return <>Open the structured detail below to review the available public campaign records for <strong>{display}</strong>.</>
  }

  return (
    <>
      Public campaign records show {activities.join(' and ')} for{' '}
      <strong>{display}</strong>. The structured detail below provides reported
      amounts, dates, recipients, and direction when the source record supplies
      it.
    </>
  )
}
