/**
 * Union index — all tracked union organizations.
 *
 * I164: split from /orgs into its own route.  Sorted by total contributed.
 */

import type { Metadata } from 'next'
import { getOrgList } from '@/lib/queries'
import OrgList from '@/components/OrgList'
import OperatorGate from '@/components/OperatorGate'
import { requireOperatorPage } from '@/lib/operator-page'

export const metadata: Metadata = {
  title: 'Unions | Richmond Commons',
  description:
    'Unions that contribute to Richmond political campaigns. See who gives, how much, and which candidates and committees receive the money.',
  robots: { index: false, follow: false },
}

export default async function UnionsPage() {
  await requireOperatorPage()

  const orgs = await getOrgList()
  const unions = orgs.filter((o) => o.entity_type === 'union')

  return (
    <OperatorGate>
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <OrgList
        orgs={unions}
        heading="Unions"
        description="Labor unions that give to Richmond political campaigns. Unions give to support labor-friendly candidates and ballot measures."
      />

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
          (California Secretary of State, Tier 1 source). Organization
          classification is auto-generated from name patterns and public
          records.
        </p>
        <p className="text-xs text-slate-400">
          Auto-generated from public records &middot; Updated within ~15
          minutes of any new filing
        </p>
      </footer>
      </div>
    </OperatorGate>
  )
}
