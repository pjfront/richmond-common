/**
 * Political-committee directory. The shared PAC/union shell is ready, but
 * public rows fail closed until the legacy aggregate carries D1 provenance
 * and D2 confidence fields. No query failure is rendered as an empty result.
 */

import type { Metadata } from 'next'
import { getPACListWithCycleBars } from '@/lib/queries'
import CampaignEntityIndex from '@/components/CampaignEntityIndex'
import type { CampaignEntityDirectoryAvailability } from '@/components/CampaignEntityIndex'
import { CampaignEntityDataError } from '@/lib/queries/campaign-entity-safety'

export const metadata: Metadata = {
  title: 'Political committees',
  description:
    'Richmond political-committee directory framework. Public rows remain withheld until provenance and confidence requirements are met.',
}

export default async function PACIndexPage() {
  const directoryResult = await getPACListWithCycleBars().then(
    () => ({ ok: true as const }),
    (error: unknown) => ({ ok: false as const, error }),
  )
  const currentYear = new Date().getFullYear()
  const currentCycle = currentYear % 2 === 0 ? currentYear : currentYear + 1
  let availability: CampaignEntityDirectoryAvailability =
    'missing-trust-fields'

  // Keep the existing bounded read so a query failure or truncated response
  // is distinguished from the known provenance/confidence blocker. The
  // aggregate is intentionally not converted into public row DTOs: it lacks
  // D1's required source fields and D2's numeric confidence score.
  if (!directoryResult.ok) {
    const { error } = directoryResult
    availability =
      error instanceof CampaignEntityDataError
        ? error.failure
        : 'query-error'
    if (!(error instanceof CampaignEntityDataError)) {
      console.error('Political committee directory query failed:', error)
    }
  }

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
