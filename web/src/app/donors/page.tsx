/**
 * Selected historical names from the legacy donor index. Its cached eligibility
 * rule is not a verified giving total or proof that a name identifies a person.
 */

import type { Metadata } from 'next'
import { getDonorList } from '@/lib/queries'
import DonorList from './DonorList'

export const metadata: Metadata = {
  title: 'Historical donor records',
  description:
    'Browse reported names and source-linked historical entries in Richmond campaign filings.',
}

export default async function DonorsPage() {
  const donors = await getDonorList()

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <DonorList donors={donors} />

      <footer className="mt-12 pt-6 border-t border-slate-100 space-y-2">
        <p className="text-xs text-slate-400 leading-relaxed">
          Historical records imported from{' '}
          <a
            href="https://public.netfile.com/pub2/?AID=RICH"
            target="_blank"
            rel="noopener noreferrer"
            className="text-civic-navy hover:underline"
          >
            NetFile
          </a>{' '}
          (City of Richmond e-filing system) and CAL-ACCESS
          (California Secretary of State).
        </p>
        <p className="text-xs text-slate-400">
          The original report links on each profile show what was filed. This historical directory is not a live filing feed.
        </p>
      </footer>
    </div>
  )
}
