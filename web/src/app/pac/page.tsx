/**
 * PAC index — operator-only V1 (S24 Phase 4, item I129 Path B).
 *
 * Lists every committee in our `committees` table that isn't tied to a
 * specific candidate (official_id IS NULL) and has at least one
 * contribution. Sorted by total raised. Each row links into the
 * /pac/[slug] profile page.
 *
 * Wrapped in <OperatorGate>; promote to public after the menu rename
 * to "Contributions" lands and the profile pages have soaked.
 */

import type { Metadata } from 'next'
import Link from 'next/link'
import { getPACList } from '@/lib/queries'
import OperatorGate from '@/components/OperatorGate'

export const metadata: Metadata = {
  title: 'Political Committees — Richmond Commons',
  description:
    'Every Richmond political committee — PACs, ballot-measure committees, and independent expenditure committees — sorted by money flowing through.',
}

function fmt(n: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(n)
}

function displayName(name: string): string {
  const beforeComma = name.split(',')[0].trim()
  return beforeComma.length >= 6 ? beforeComma : name
}

export default async function PACIndexPage() {
  const pacs = await getPACList()
  const totalRaised = pacs.reduce((s, p) => s + p.total_raised, 0)

  return (
    <OperatorGate>
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <header className="mb-8">
          <h1 className="text-3xl font-bold text-civic-navy">
            Political committees
          </h1>
          <p className="text-slate-600 mt-2 leading-relaxed">
            Committees that raise money to support or oppose Richmond
            candidates and ballot measures, but that aren&apos;t controlled by
            a candidate themselves. This includes PACs, union-sponsored
            committees, and ballot-measure committees.
          </p>
          <p className="text-slate-500 mt-3 text-sm leading-relaxed">
            <strong className="text-civic-navy">{pacs.length}</strong>{' '}
            committees with a combined{' '}
            <strong className="text-civic-navy tabular-nums">{fmt(totalRaised)}</strong>{' '}
            raised across all years.
          </p>
        </header>

        <div className="grid gap-2">
          {pacs.map((pac) => (
            <Link
              key={pac.id}
              href={`/pac/${pac.slug}`}
              className="flex items-start justify-between gap-4 py-3 px-4 rounded-lg border border-slate-100 hover:border-civic-navy/20 hover:bg-slate-50/80 transition-all group"
            >
              <div className="min-w-0 flex-1">
                <div className="font-medium text-sm text-civic-navy group-hover:underline">
                  {displayName(pac.name)}
                </div>
                {pac.sponsor_disclosure && (
                  <div className="text-xs text-civic-amber mt-0.5">
                    {pac.sponsor_disclosure}
                  </div>
                )}
                <div className="text-xs text-slate-400 mt-0.5">
                  {pac.donor_count} donor{pac.donor_count === 1 ? '' : 's'}
                  {pac.contribution_count !== pac.donor_count && (
                    <> &middot; {pac.contribution_count} contributions</>
                  )}
                </div>
              </div>
              <span className="text-sm text-slate-600 tabular-nums shrink-0 mt-0.5">
                {fmt(pac.total_raised)}
              </span>
            </Link>
          ))}
        </div>

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
