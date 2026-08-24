/** Sentence-led index row without an unbenchmarked headline metric. */

import Link from 'next/link'
import type { ReactNode } from 'react'
import type { PACWithCycleBars } from '@/lib/queries'

interface Props {
  pac: PACWithCycleBars
  currentCycle: number
}

function displayName(name: string): string {
  const beforeComma = name.split(',')[0].trim()
  return beforeComma.length >= 6 ? beforeComma : name
}

function renderLede(pac: PACWithCycleBars, currentCycle: number): ReactNode {
  const hasCurrentIncoming = pac.current_cycle_in > 0
  const hasCurrentOutgoing = pac.current_cycle_out > 0
  const hasEarlierActivity = pac.cycle_bars.some(
    (cycle) =>
      cycle.cycle !== currentCycle &&
      (cycle.in_total > 0 || cycle.out_total > 0),
  )

  if (hasCurrentIncoming && hasCurrentOutgoing) {
    return (
      <>
        Public campaign records show money received and contributions to other
        committees in the current election cycle.
      </>
    )
  }
  if (hasCurrentIncoming) {
    return (
      <>Public campaign records show money received in the current election cycle.</>
    )
  }
  if (hasCurrentOutgoing) {
    return (
      <>
        Public campaign records show contributions to other committees in the
        current election cycle.
      </>
    )
  }
  if (hasEarlierActivity) {
    return (
      <>
        Public campaign records show earlier activity, but none in the current
        election cycle.
      </>
    )
  }
  return <>Open the profile to review the available public campaign records.</>
}

export default function PACRow({ pac, currentCycle }: Props) {
  const display = displayName(pac.name)
  return (
    <Link
      href={`/pac/${pac.slug}`}
      className="group flex min-h-11 items-start gap-4 rounded-lg border border-slate-200 px-4 py-3 transition-all hover:border-civic-navy/30 hover:bg-slate-50/80 focus:outline-none focus:ring-2 focus:ring-civic-navy focus:ring-offset-2"
    >
      <div className="min-w-0 flex-1">
        <h2 className="text-base font-semibold text-civic-navy group-hover:underline">
          {display}
        </h2>
        {pac.sponsor_disclosure ? (
          <p className="mt-1 text-sm font-medium text-amber-800">
            {pac.sponsor_disclosure}
          </p>
        ) : null}
        <p className="mt-1 text-sm leading-relaxed text-slate-700">
          {renderLede(pac, currentCycle)}
        </p>
      </div>
      <span
        aria-hidden="true"
        className="shrink-0 self-center text-xl text-slate-300 transition-colors group-hover:text-civic-navy-light"
      >
        &rarr;
      </span>
    </Link>
  )
}
