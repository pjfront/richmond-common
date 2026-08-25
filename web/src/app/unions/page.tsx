/**
 * Union index — all tracked union organizations.
 *
 * I164: split from /orgs into its own route.  Sorted by total contributed.
 */

import type { Metadata } from 'next'
import { getOrgList } from '@/lib/queries'
import CampaignEntityIndex from '@/components/CampaignEntityIndex'
import type { CampaignEntityIndexItem } from '@/components/CampaignEntityIndex'

export const metadata: Metadata = {
  title: 'Unions',
  description:
    'Unions that contribute to Richmond political campaigns. See who gives, how much, and which candidates and committees receive the money.',
}

export default async function UnionsPage() {
  const orgs = await getOrgList()
  const unions = orgs.filter((o) => o.entity_type === 'union')
  const currentYear = new Date().getFullYear()
  const defaultCycle = currentYear % 2 === 0 ? currentYear : currentYear + 1
  const currentCycle = Math.max(
    ...unions.flatMap((union) => union.cycle_bars.map((bar) => bar.cycle)),
    defaultCycle,
  )
  const items: CampaignEntityIndexItem[] = unions.map((union) => ({
    id: union.slug,
    href: `/orgs/${union.slug}`,
    name: union.display_name,
    kind: 'union',
    sponsorDisclosure: union.sponsor_disclosure,
    cycleBars: union.cycle_bars.map((bar) => ({
      cycle: bar.cycle,
      received: 0,
      given: bar.total,
    })),
  }))

  return (
    <CampaignEntityIndex
      heading="Unions"
      description="Labor organizations that appear as donors in Richmond campaign-finance filings. Open a profile to review reported recipients, dates, amounts, and independent spending when available."
      items={items}
      currentCycle={currentCycle}
      singularLabel="union"
      pluralLabel="unions"
      sourceNote={
        <>
          Organization type is auto-generated from filing names and public
          records. Treat the label as a filing-based classification, not a
          statement about an organization&apos;s goals.
        </>
      }
    />
  )
}
