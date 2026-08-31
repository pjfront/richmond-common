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
 * Publication tier: Operator-only through the November treatment T14 review.
 */

import type { Metadata } from 'next'
import { getPACListWithCycleBars } from '@/lib/queries'
import OperatorGate from '@/components/OperatorGate'
import { requireOperatorPage } from '@/lib/operator-page'
import PACIndexClient from './PACIndexClient'

export const metadata: Metadata = {
  title: 'Political Action Committees | Richmond Commons',
  description:
    'Every Richmond political action committee that influences elections without being controlled by a candidate. Includes general-purpose PACs, independent-expenditure committees, and ballot-measure committees.',
  robots: { index: false, follow: false },
}

export default async function PACIndexPage() {
  await requireOperatorPage()

  const pacs = await getPACListWithCycleBars()

  // currentCycle is computed from the data so a future test fixture
  // doesn't need to know what year it is. PACIndexClient owns the
  // temporal-filter UI and the sort order within the selected window;
  // each row's lede prose still narrates current-cycle activity, with
  // the sparkline carrying the historical context.
  const currentCycle = Math.max(
    ...pacs.flatMap((p) => p.cycle_bars.map((b) => b.cycle)),
    new Date().getFullYear(),
  )

  return (
    <OperatorGate>
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <header className="mb-6">
        <h1 className="text-3xl font-bold text-civic-navy">
          Political action committees
        </h1>
        <p className="text-slate-600 mt-2 leading-relaxed max-w-3xl">
          Committees that raise money to support or oppose Richmond
          candidates and ballot measures, but that aren&apos;t
          controlled by any candidate. Includes general-purpose PACs
          (often union-sponsored), independent-expenditure committees,
          and ballot-measure committees.
        </p>
      </header>

      <div className="mb-6 max-w-3xl rounded-md bg-slate-50 border border-slate-200 px-4 py-3 text-xs text-slate-600 leading-relaxed">
        <p className="font-semibold text-slate-700 mb-1">
          How PACs differ from candidate campaigns
        </p>
        <p className="mb-1.5">
          Individual donors can give a candidate&apos;s campaign at most{' '}
          <strong>$2,500</strong> per election (the City of Richmond
          contribution limit). PACs face <strong>no per-donor cap</strong>:
          a single donor can give a PAC tens of thousands of dollars.
          That&apos;s the structural reason PACs exist; it&apos;s also
          why a PAC&apos;s top donors matter more individually than a
          candidate&apos;s.
        </p>
        <p>
          <strong>Independent-expenditure (IE) committees</strong> spend
          money on ads supporting or opposing a candidate without
          coordinating with that candidate&apos;s campaign.{' '}
          <strong>Ballot-measure committees</strong> raise money for or
          against a specific ballot measure. Both kinds appear here
          alongside general-purpose PACs.
        </p>
      </div>

      <p className="text-xs text-slate-500 mb-6 leading-relaxed bg-civic-amber/[0.04] border-l-2 border-civic-amber/40 px-3 py-2 max-w-3xl">
        PAC activity for any election typically surges in the final
        two weeks before voting. The {currentCycle} cycle is still early.
        Most committees are coasting on prior-cycle activity for now.
        Check back closer to election day.
      </p>

      <PACIndexClient pacs={pacs} currentCycle={currentCycle} />

      <footer className="mt-12 pt-6 border-t border-slate-100 space-y-2">
        <p className="text-xs text-slate-400 leading-relaxed">
          Data from{' '}
          <a
            href="https://public.netfile.com/pub2/?AID=RICH"
            target="_blank"
            rel="noopener noreferrer"
            className="text-civic-navy hover:underline"
          >
            NetFile
          </a>{' '}
          and CAL-ACCESS (California Secretary of State). Both Tier 1
          sources. Updated within ~15 minutes of any new filing.
        </p>
      </footer>
      </div>
    </OperatorGate>
  )
}
