/**
 * Union directory. The shared PAC/union shell is ready, but name-only union
 * classifications remain withheld from public summary counts under D2.
 */

import type { Metadata } from 'next'
import { getCompleteOrgList } from '@/lib/queries'
import CampaignEntityIndex from '@/components/CampaignEntityIndex'
import type { CampaignEntityDirectoryAvailability } from '@/components/CampaignEntityIndex'

export const metadata: Metadata = {
  title: 'Unions',
  description:
    'Richmond union-directory framework. Public rows remain withheld until provenance and confidence requirements are met.',
}

export default async function UnionsPage() {
  // Production refresh failures escape so ISR keeps serving the last
  // successful render. The explicit inert CI build skips the read entirely;
  // that boundary cannot occur through an absent or misspelled value.
  if (process.env.RICHMOND_BUILD_USES_PRODUCTION_DATA !== 'false') {
    await getCompleteOrgList()
  }
  const currentYear = new Date().getFullYear()
  const currentCycle = currentYear % 2 === 0 ? currentYear : currentYear + 1
  const availability: CampaignEntityDirectoryAvailability =
    'missing-trust-fields'

  // Donor entity_type is currently generated from filing-name patterns. Read
  // completeness is still verified, but no union row becomes a public summary
  // item until its classification has stored confidence >= 90% and the row
  // has complete provenance.

  return (
    <CampaignEntityIndex
      heading="Unions"
      description="This directory is intended to organize labor-organization filing records in the same format as political committees."
      items={[]}
      currentCycle={currentCycle}
      singularLabel="union"
      pluralLabel="unions"
      availability={availability}
      sourceNote={
        <>
          Current organization types are inferred from filing-name patterns
          alone. Because that process has no stored numeric confidence, its
          union labels are withheld from this public summary.
        </>
      }
    />
  )
}
