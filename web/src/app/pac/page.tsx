/** Public sentence-led list of Richmond political committees. */

import type { Metadata } from 'next'
import { getPACListWithCycleBars } from '@/lib/queries'
import { orderPACsForIndex } from '@/lib/pac-index-order'
import PACRow from './PACRow'

export const metadata: Metadata = {
  title: 'Political Action Committees | Richmond Commons',
  description:
    'Every Richmond political action committee that influences elections without being controlled by a candidate. Includes general-purpose PACs, independent-expenditure committees, and ballot-measure committees.',
}

export default async function PACIndexPage() {
  const pacs = await getPACListWithCycleBars()
  const orderedPacs = orderPACsForIndex(pacs)

  // Current-cycle totals support the sentence in each row. The historical
  // bars are not rendered; they are only used to identify the last active
  // cycle when a committee has no current activity.
  const currentCycle = Math.max(
    ...pacs.flatMap((p) => p.cycle_bars.map((b) => b.cycle)),
    new Date().getFullYear(),
  )

  return (
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

      <div className="mb-6 max-w-3xl rounded-md bg-slate-50 border border-slate-200 px-4 py-3 text-sm text-slate-700 leading-relaxed">
        <p className="font-semibold text-slate-700 mb-1">
          How PACs differ from candidate campaigns
        </p>
        <p className="mb-2">
          A political action committee is separate from a candidate&apos;s
          campaign. Contribution rules vary by committee type, so this site
          reports what each official filing lists instead of assigning a
          motive to a donor or committee.
        </p>
        <p>
          Independent-expenditure committees report spending that supports or
          opposes a candidate without giving that money to the candidate&apos;s
          campaign. Ballot-measure committees report activity for or against a
          measure. Both appear here alongside other political committees.
        </p>
      </div>

      <p className="text-sm text-slate-600 mb-4 leading-relaxed max-w-3xl">
        {pacs.length} committee{pacs.length === 1 ? '' : 's'} with tracked
        filings. Each sentence describes activity in the {currentCycle}{' '}
        election cycle and, when useful, the most recent earlier cycle.
      </p>

      {orderedPacs.length > 0 ? (
        <div className="grid gap-3 mb-8">
          {orderedPacs.map((pac) => (
            <PACRow key={pac.id} pac={pac} currentCycle={currentCycle} />
          ))}
        </div>
      ) : (
        <div className="mb-8 rounded-lg border border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-600">
          No political-committee filings are available yet.
        </div>
      )}

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
  )
}

