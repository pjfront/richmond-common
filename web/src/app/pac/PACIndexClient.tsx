'use client'

/**
 * PACIndexClient. Client wrapper around the PAC list rows that owns
 * the temporal filter state. Defaults to current cycle ("2026" right
 * now, computed from the data); toggles open to last-two-cycles or
 * all-time. Hides PACs with zero activity in the selected window.
 *
 * The lede prose inside each row already adapts to current vs.
 * historical activity (see renderLede on the server page), so this
 * component only handles the filter set + sort behavior. Each row
 * stays a server-rendered <PACRow> passed in via children — the
 * client component just decides which children to display.
 */

import { useMemo, useState } from 'react'
import type { PACWithCycleBars } from '@/lib/queries'
import PACRow from './PACRow'

type Window = 'current' | 'last2' | 'all'

interface Props {
  pacs: PACWithCycleBars[]
  currentCycle: number
}

function totalInWindow(pac: PACWithCycleBars, window: Window, currentCycle: number): number {
  if (window === 'all') return pac.total_raised
  const cutoff = window === 'current' ? currentCycle : currentCycle - 2
  let sum = 0
  for (const b of pac.cycle_bars) {
    if (b.cycle >= cutoff) sum += b.in_total + b.out_total
  }
  return sum
}

export default function PACIndexClient({ pacs, currentCycle }: Props) {
  const [windowSel, setWindowSel] = useState<Window>('current')

  const { visible, hiddenCount } = useMemo(() => {
    const visible: PACWithCycleBars[] = []
    let hidden = 0
    for (const p of pacs) {
      const t = totalInWindow(p, windowSel, currentCycle)
      if (t > 0) visible.push(p)
      else hidden += 1
    }
    visible.sort(
      (a, b) =>
        totalInWindow(b, windowSel, currentCycle) -
        totalInWindow(a, windowSel, currentCycle),
    )
    return { visible, hiddenCount: hidden }
  }, [pacs, windowSel, currentCycle])

  const labels: Record<Window, string> = {
    current: `${currentCycle} cycle`,
    last2: `${currentCycle - 2} – ${currentCycle}`,
    all: 'All time',
  }
  const sublabels: Record<Window, string> = {
    current: 'Active right now',
    last2: 'Last two election cycles',
    all: 'Lifetime contributions',
  }

  return (
    <>
      <div className="mb-6">
        <div className="flex flex-wrap items-stretch gap-2">
          {(['current', 'last2', 'all'] as Window[]).map((w) => {
            const active = windowSel === w
            return (
              <button
                key={w}
                type="button"
                onClick={() => setWindowSel(w)}
                aria-pressed={active}
                className={`group flex flex-col items-start text-left rounded-lg px-4 py-2.5 border transition-all ${
                  active
                    ? 'bg-civic-amber border-civic-amber text-white shadow-sm'
                    : 'bg-white border-slate-200 text-slate-700 hover:border-civic-amber/60 hover:bg-civic-amber/[0.04]'
                }`}
              >
                <span className="text-sm font-semibold tabular-nums">{labels[w]}</span>
                <span
                  className={`text-[11px] leading-tight mt-0.5 ${
                    active ? 'text-white/85' : 'text-slate-500 group-hover:text-slate-600'
                  }`}
                >
                  {sublabels[w]}
                </span>
              </button>
            )
          })}
        </div>
        <p className="text-xs text-slate-500 mt-2 leading-relaxed" aria-live="polite">
          Showing <strong>{visible.length}</strong> committee{visible.length === 1 ? '' : 's'} with
          activity {windowSel === 'current' ? `in the ${currentCycle} cycle` : windowSel === 'last2' ? `in the ${currentCycle - 2} or ${currentCycle} cycles` : 'across any tracked cycle'}.
          {hiddenCount > 0 && windowSel !== 'all' && (
            <>
              {' '}<button
                type="button"
                onClick={() => setWindowSel('all')}
                className="text-civic-navy underline-offset-2 hover:underline"
              >
                {hiddenCount} more committee{hiddenCount === 1 ? '' : 's'} are quiet right now &rarr;
              </button>
            </>
          )}
        </p>
      </div>

      {visible.length > 0 ? (
        <div className="grid gap-3 mb-8">
          {visible.map((p) => (
            <PACRow key={p.id} pac={p} currentCycle={currentCycle} />
          ))}
        </div>
      ) : (
        <div className="mb-8 rounded-lg border border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
          No committees have activity in this window.
        </div>
      )}
    </>
  )
}
