/**
 * PACRow — a single sentence-led list row for a PAC on the index
 * page. Pure-render component (no server-only features) so it can be
 * rendered from either the server page directly or the client-side
 * PACIndexClient as it filters the visible set.
 *
 * The lede prose is structured: orientation (what is this committee)
 * → current-cycle action → historical context if quiet. No leading
 * dollar amounts; numbers serve the sentence.
 */

import Link from 'next/link'
import type { ReactNode } from 'react'
import type { PACWithCycleBars } from '@/lib/queries'
import CycleBarsSparkline from './CycleBarsSparkline'

interface Props {
  pac: PACWithCycleBars
  currentCycle: number
  compact?: boolean
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

export default function PACRow({ pac, currentCycle, compact }: Props) {
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
