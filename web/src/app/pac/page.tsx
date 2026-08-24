/** Public sentence-led list of Richmond political committees. */

import type { Metadata } from 'next'
import { getPACListWithCycleBars } from '@/lib/queries'
import { orderPACsForIndex } from '@/lib/pac-index-order'
import PACRow from './PACRow'

export const metadata: Metadata = {
  title: 'Political action committees',
  description:
    'Richmond political committees listed in tracked public campaign-finance records, including general-purpose PACs, independent-expenditure committees, and ballot-measure committees.',
}

export default async function PACIndexPage() {
  const pacs = await getPACListWithCycleBars()
  const orderedPacs = orderPACsForIndex(pacs)
  const currentCycle = Math.max(
    ...pacs.flatMap((pac) => pac.cycle_bars.map((cycle) => cycle.cycle)),
    new Date().getFullYear(),
  )

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <header className="mb-6">
        <h1 className="text-3xl font-bold text-civic-navy">
          Political action committees
        </h1>
        <p className="text-slate-600 mt-2 leading-relaxed max-w-3xl">
          Committees that raise money to support or oppose Richmond candidates
          and ballot measures, but that aren&apos;t controlled by any
          candidate. Includes general-purpose PACs, independent-expenditure
          committees, and ballot-measure committees.
        </p>
      </header>

      <div className="mb-6 max-w-3xl rounded-md bg-slate-50 border border-slate-200 px-4 py-3 text-sm text-slate-700 leading-relaxed">
        <p className="font-semibold text-slate-700 mb-1">
          How PACs differ from candidate campaigns
        </p>
        <p className="mb-2">
          A political action committee is separate from a candidate&apos;s
          campaign. Contribution rules vary by committee type, so this site
          reports what each official record lists instead of assigning a
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
        Open a committee profile for the available filing detail. Each sentence
        distinguishes current-cycle activity from earlier tracked activity.
      </p>

      {orderedPacs.length > 0 ? (
        <div className="grid gap-3 mb-8">
          {orderedPacs.map((pac) => (
            <PACRow key={pac.id} pac={pac} currentCycle={currentCycle} />
          ))}
        </div>
      ) : (
        <div className="mb-8 rounded-lg border border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-600">
          No political-committee records are available yet.
        </div>
      )}

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
          and CAL-ACCESS (California Secretary of State), both Tier 1 official
          sources.
        </p>
      </footer>
    </div>
  )
}
