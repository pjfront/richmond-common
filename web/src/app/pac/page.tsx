/**
 * PAC index V2 (operator-only). Sentence-led list of political
 * committees, with per-row cycle-bars sparkline answering "how does the
 * current cycle compare historically." Replaces the V1 dollar-sorted
 * list per the operator's framing critique 2026-04-29:
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
 */

import type { Metadata } from 'next'
import Link from 'next/link'
import type { ReactNode } from 'react'
import { getPACListWithCycleBars } from '@/lib/queries'
import type { PACWithCycleBars } from '@/lib/queries'
import OperatorGate from '@/components/OperatorGate'
import CycleBarsSparkline from './CycleBarsSparkline'

export const metadata: Metadata = {
  title: 'Political Action Committees | Richmond Commons',
  description:
    'Every Richmond political action committee that influences elections without being controlled by a candidate. Includes general-purpose PACs, independent-expenditure committees, and ballot-measure committees.',
}

function fmt(n: number): string {
  if (n === 0) return '$0'
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
  const pacs = await getPACListWithCycleBars()

  // Sort by lifetime total raised, descending. Surfaces the historically
  // heavyweight committees first (RPOA, IAFF Local 188, East Bay Working
  // Families, Coalition for Richmond's Future) regardless of where they
  // sit in the current beat. Each row's lede still narrates current-cycle
  // activity; the cycle-bars sparkline carries the historical context.
  const currentCycle = Math.max(
    ...pacs.flatMap((p) => p.cycle_bars.map((b) => b.cycle)),
    new Date().getFullYear(),
  )
  const sorted = [...pacs].sort((a, b) => b.total_raised - a.total_raised)

  return (
    <OperatorGate>
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
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
          two weeks before voting. The 2026 cycle is still early. Most
          committees you see below are coasting on prior-cycle activity
          for now. Check back closer to election day.
        </p>

        {sorted.length > 0 && (
          <div className="grid gap-3 mb-8">
            {sorted.map((p) => (
              <PACRow key={p.id} pac={p} currentCycle={currentCycle} />
            ))}
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
    </OperatorGate>
  )
}

interface PACRowProps {
  pac: PACWithCycleBars
  currentCycle: number
  compact?: boolean
}

function PACRow({ pac, currentCycle, compact }: PACRowProps) {
  const display = displayName(pac.name)
  return (
    <Link
      href={`/pac/${pac.slug}`}
      className={`flex items-start gap-4 py-3 px-4 rounded-lg border border-slate-100 hover:border-civic-navy/30 hover:bg-slate-50/80 transition-all group ${compact ? 'opacity-75' : ''}`}
    >
      <div className="min-w-0 flex-1">
        <div className="text-sm leading-relaxed text-slate-700">
          {renderLede(pac, display, currentCycle)}
        </div>
      </div>
      <div className="shrink-0 mt-0.5">
        <CycleBarsSparkline bars={pac.cycle_bars} currentCycle={currentCycle} />
      </div>
    </Link>
  )
}

/** Sentence-led row content. Orientation first (what is this PAC),
 *  then current-cycle action, then historical context if relevant.
 *  No leading dollar amounts. Numbers serve the sentence. */
function renderLede(
  pac: PACWithCycleBars,
  display: string,
  currentCycle: number,
): ReactNode {
  const sponsor = pac.sponsor_disclosure
  const currentTotal = pac.current_cycle_in + pac.current_cycle_out
  const lastActive = (() => {
    for (let i = pac.cycle_bars.length - 1; i >= 0; i--) {
      const b = pac.cycle_bars[i]
      if (b.in_total > 0 || b.out_total > 0) return b.cycle
    }
    return null
  })()

  // Orientation phrase
  const orientation: ReactNode = sponsor ? (
    <>
      <span className="font-medium text-civic-navy group-hover:underline">{display}</span>.{' '}
      <span className="text-civic-amber">{sponsor}.</span>
    </>
  ) : (
    <>
      <span className="font-medium text-civic-navy group-hover:underline">{display}</span>.{' '}
    </>
  )

  // Current-cycle status
  let action: ReactNode
  if (currentTotal > 0) {
    if (pac.current_cycle_in > 0 && pac.current_cycle_out > 0) {
      action = (
        <>
          {' '}Active in the {currentCycle} cycle: raised{' '}
          <strong>{fmt(pac.current_cycle_in)}</strong>, contributed{' '}
          <strong>{fmt(pac.current_cycle_out)}</strong> to other committees.
        </>
      )
    } else if (pac.current_cycle_in > 0) {
      action = (
        <>
          {' '}Raised <strong>{fmt(pac.current_cycle_in)}</strong> so far in the{' '}
          {currentCycle} cycle.
        </>
      )
    } else {
      action = (
        <>
          {' '}Contributed <strong>{fmt(pac.current_cycle_out)}</strong> to other
          committees so far in the {currentCycle} cycle.
        </>
      )
    }
  } else if (lastActive !== null) {
    action = (
      <>
        {' '}Quiet so far in the {currentCycle} cycle. Last active in{' '}
        <strong>{lastActive}</strong>.
      </>
    )
  } else {
    action = <> No tracked activity yet.</>
  }

  return (
    <>
      {orientation}
      {action}
    </>
  )
}
