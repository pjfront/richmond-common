/**
 * PAC index. Sentence-led list of political committees, with per-row
 * cycle-bars sparkline answering "how does the current cycle compare
 * historically." Replaces the V1 dollar-sorted list per the operator's
 * framing critique 2026-04-29:
 *   - Mission framing: who they're supporting now, NOT how much
 *     we've tracked
 *   - Three priorities in order: current support, current dollars,
 *     historical context
 *   - Visualization is the entry surface, not the destination
 *
 * Design follows docs/design/PAC-MATRIX-DESIGN.md three-layer template
 * (Explore, Temporal, Receipt). At the index, the per-row sparkline
 * absorbs the temporal layer at low density; the full matrix lives one
 * click in on the profile page.
 *
 * Publication tier: Public. Graduated from operator-only 2026-07-06 (S28.4).
 */

import type { Metadata } from 'next'
import { getPACListWithCycleBars } from '@/lib/queries'
import CampaignEntityIndex from '@/components/CampaignEntityIndex'
import type { CampaignEntityIndexItem } from '@/components/CampaignEntityIndex'

export const metadata: Metadata = {
  title: 'Political committees',
  description:
    'Committees with reported activity in Richmond elections, including general-purpose, independent-spending, and ballot-measure committees.',
}

export default async function PACIndexPage() {
  const pacs = await getPACListWithCycleBars()
  const currentYear = new Date().getFullYear()
  const defaultCycle = currentYear % 2 === 0 ? currentYear : currentYear + 1

  // Compute the cycle from the data so future fixtures do not need to know
  // the wall-clock year. The shared directory owns filtering and ordering.
  const currentCycle = Math.max(
    ...pacs.flatMap((p) => p.cycle_bars.map((b) => b.cycle)),
    defaultCycle,
  )

  const items: CampaignEntityIndexItem[] = pacs.map((pac) => ({
    id: pac.id,
    href: `/pac/${pac.slug}`,
    name: displayName(pac.name),
    kind: 'committee',
    sponsorDisclosure: pac.sponsor_disclosure,
    cycleBars: pac.cycle_bars.map((bar) => ({
      cycle: bar.cycle,
      received: bar.in_total,
      given: bar.out_total,
    })),
  }))

  return (
    <CampaignEntityIndex
      heading="Political committees"
      description="Committees with reported activity in Richmond elections, including general-purpose, independent-spending, and ballot-measure committees. Open a profile to review the available filing detail."
      items={items}
      currentCycle={currentCycle}
      singularLabel="committee"
      pluralLabel="committees"
      afterList={
        <section className="rounded-lg border border-slate-200 bg-slate-50 p-5">
          <h2 className="text-lg font-semibold text-civic-navy">
            How these committees differ from candidate campaigns
          </h2>
          <p className="mt-2 text-base leading-7 text-slate-700">
            Independent-spending committees report spending that is not
            coordinated with a candidate&apos;s campaign. Ballot-measure
            committees report activity for or against a measure. Both appear
            here alongside general-purpose committees.
          </p>
        </section>
      }
    />
  )
}

function displayName(name: string): string {
  const beforeComma = name.split(',')[0].trim()
  return beforeComma.length >= 6 ? beforeComma : name
}
