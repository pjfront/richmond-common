/** Company index — tracked company and business-group donors. */

import type { Metadata } from 'next'
import { getOrgList } from '@/lib/queries'
import OrgList from '@/components/OrgList'

export const metadata: Metadata = {
  title: 'Companies',
  description:
    'Companies and business groups listed as donors in Richmond campaign-finance records, with links to their available record detail.',
}

export default async function CompaniesPage() {
  const orgs = await getOrgList()
  const companies = orgs.filter((org) => org.entity_type === 'corporation')

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <OrgList
        orgs={companies}
        heading="Companies"
        description="Companies and business groups listed as donors in Richmond campaign-finance records. Open a profile to review the available recipient and filing detail."
      />

      <footer className="mt-12 pt-6 border-t border-slate-100 space-y-2">
        <p className="text-xs text-slate-500 leading-relaxed">
          Public campaign records come from{' '}
          <a
            href="https://public.netfile.com/pub2/?AID=RICH"
            target="_blank"
            rel="noopener noreferrer"
            className="text-civic-navy underline-offset-2 hover:underline"
          >
            NetFile
          </a>{' '}
          and CAL-ACCESS, both Tier 1 official sources. Organization
          classification is auto-generated from record names and public
          records.
        </p>
      </footer>
    </div>
  )
}
