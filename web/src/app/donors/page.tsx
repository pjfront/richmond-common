/**
 * Individual donor index — S28.6, Graduated tier.
 *
 * Lists all individual donors whose aggregate giving across all cycles
 * exceeds $5,000 (Option b, resolved 2026-07-06 per #72).
 *
 * Follows the /unions and /corporations pattern (S28.3).
 */

import type { Metadata } from 'next'
import { getDonorList } from '@/lib/queries'
import DonorList from './DonorList'

export const metadata: Metadata = {
  title: 'Individual Donors',
  description:
    'Individual donors who have contributed $5,000 or more to Richmond political campaigns. All data from public campaign-finance filings.',
}

export default async function DonorsPage() {
  const donors = await getDonorList()

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <DonorList donors={donors} />

      <footer className="mt-12 pt-6 border-t border-slate-100 space-y-2">
        <p className="text-xs text-slate-400 leading-relaxed">
          Showing individual donors with at least $5,000 in total tracked
          contributions. All contribution data from{' '}
          <a
            href="https://public.netfile.com/pub2/?AID=RICH"
            target="_blank"
            rel="noopener noreferrer"
            className="text-civic-navy hover:underline"
          >
            NetFile
          </a>{' '}
          (City of Richmond e-filing system, Tier 1 source) and CAL-ACCESS
          (California Secretary of State, Tier 1 source).
        </p>
        <p className="text-xs text-slate-400">
          Auto-generated from public records &middot; Updated within ~15
          minutes of any new filing
        </p>
      </footer>
    </div>
  )
}
