/**
 * Political-committee directory. The shared PAC/union shell is ready, but
 * public rows fail closed until the legacy aggregate carries D1 provenance
 * and D2 confidence fields. No query failure is rendered as an empty result.
 */

import type { Metadata } from 'next'
import { getPACListWithCycleBars } from '@/lib/queries'
import CampaignEntityIndex from '@/components/CampaignEntityIndex'
import type { CampaignEntityDirectoryAvailability } from '@/components/CampaignEntityIndex'

export const metadata: Metadata = {
  title: 'Political committees',
  description:
    'Richmond political-committee directory framework. Public rows remain withheld until provenance and confidence requirements are met.',
}

export default async function PACIndexPage() {
  // Production refresh failures escape so ISR keeps serving the last
  // successful render. The explicit inert CI build skips the read entirely;
  // that boundary cannot occur through an absent or misspelled value.
  if (process.env.RICHMOND_BUILD_USES_PRODUCTION_DATA !== 'false') {
    await getPACListWithCycleBars()
  }
  const currentYear = new Date().getFullYear()
  const currentCycle = currentYear % 2 === 0 ? currentYear : currentYear + 1
  const availability: CampaignEntityDirectoryAvailability =
    'missing-trust-fields'

  // Keep the bounded read until the operator chooses this placeholder's
  // publication treatment. The aggregate is intentionally not converted into
  // public row DTOs: it lacks D1 source fields and D2 numeric confidence.

  return (
    <CampaignEntityIndex
      heading="Political committees"
      description="This directory is intended to organize general-purpose, independent-spending, and ballot-measure committee filings in one consistent format."
      items={[]}
      currentCycle={currentCycle}
      singularLabel="committee"
      pluralLabel="committees"
      availability={availability}
      afterList={
        <section className="rounded-lg border border-slate-200 bg-slate-50 p-5">
          <h2 className="text-lg font-semibold text-civic-navy">
            How these committees differ from candidate campaigns
          </h2>
          <p className="mt-2 text-base leading-7 text-slate-700">
            Independent-spending committees report spending that is not
            coordinated with a candidate&apos;s campaign. Ballot-measure
            committees report activity for or against a measure. The planned
            directory will organize both alongside general-purpose
            committees once its trust fields are complete.
          </p>
        </section>
      }
    />
  )
}
