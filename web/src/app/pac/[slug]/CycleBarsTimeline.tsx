'use client'

/**
 * CycleBarsTimeline. The cycle mirror: a temporal middle layer for the
 * PAC profile page that redraws in response to the matrix selection
 * above. Named "the sixth structural move" of the Explore-then-detail
 * grammar in docs/design/INTERACTIVE-DATA-VIZ.md (2026-04-29).
 *
 * Modes (driven by selection state):
 *   - null: page-level. Bars show the PAC's total intake (or outflow)
 *     per cycle, answering "how active is this committee historically."
 *   - donor: bars show this donor's contributions to this PAC per cycle.
 *   - candidate: bars show this PAC's outflows to this candidate per
 *     cycle.
 *   - cell: bars show the per-cycle proportional attribution from this
 *     donor, through the PAC, to this candidate. Same math the matrix
 *     uses, broken out by cycle.
 *
 * Y-axis toggle: dollars vs. share-of-cycle. Per The Pudding's "In
 * pursuit of democracy" pattern. Share-of-cycle answers "is 2024
 * actually big in absolute terms or just relative to a busier overall
 * environment." Defaults to dollars.
 *
 * The faint "all pairs" baseline behind the selected series is
 * recommended by the research but deferred to a follow-up; would
 * require a second computed series and additional SVG layering.
 *
 * Election-day tick lines are also deferred. Cycle-bars represent
 * 2-year buckets; an inline tick within each bar at "late in the
 * cycle" needs a more careful visual choice than the V1 timeline
 * earns.
 */

import { useMemo, useState } from 'react'
import type { PACFlowMatrix } from '@/lib/queries'
import type { PACContributionRow, PACOutgoingRow } from '@/lib/types'
import type { Selection } from './PACProfileDashboard'

interface Props {
  /** Matrix is optional. When absent (PACs whose outflows don't trace
   *  to candidates), the timeline still shows page-level cycles derived
   *  from the contribution/outgoing dates. Selection-driven modes only
   *  fire when a matrix is present, so we never need its detail here
   *  beyond the cycles list. */
  matrix: PACFlowMatrix | null
  contributions: PACContributionRow[]
  outgoing: PACOutgoingRow[]
  pacDisplay: string
  selection: Selection
  /** When non-null, this cycle is the active focus (set by clicking a
   *  bar). The active bar gets a highlight ring; the others appear
   *  normally so the reader still sees the historical context. */
  cycleFocus: number | null
  /** Called when the user clicks a bar. Pass the cycle to focus, or
   *  null to clear (when clicking the same bar again). */
  onCycleFocus: (cycle: number | null) => void
}

type Mode = 'dollars' | 'share'

interface CycleBar {
  cycle: number
  /** Selected entity's amount in this cycle (dollars). */
  selected: number
  /** Whole-PAC reference total in this cycle (intake for inflow modes,
   *  outflow for outgoing modes). Used for share-of-cycle and as a
   *  context number in the tooltip. */
  reference: number
  /** Selected as a fraction of reference (0..1). */
  share: number
}

function fmt(n: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(n)
}

function fmtShort(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`
  if (n >= 10_000) return `$${Math.round(n / 1000)}k`
  if (n >= 1_000) return `$${(n / 1000).toFixed(1)}k`
  if (n > 0) return `$${Math.round(n)}`
  return '–'
}

function pct(p: number): string {
  if (p <= 0) return '0%'
  if (p >= 0.01) return `${Math.round(p * 100)}%`
  return '<1%'
}

function cycleOf(dateIso: string): number | null {
  const year = parseInt(dateIso.slice(0, 4), 10)
  if (Number.isNaN(year)) return null
  return year % 2 === 0 ? year : year + 1
}

export default function CycleBarsTimeline({
  matrix,
  contributions,
  outgoing,
  pacDisplay,
  selection,
  cycleFocus,
  onCycleFocus,
}: Props) {
  const [mode, setMode] = useState<Mode>('dollars')
  // Hover state lets us paint the affordance directly on the bar via
  // inline JSX attributes — Tailwind hover variants don't reliably win
  // over JSX `stroke=` attributes in SVG, so we drive the stroke
  // ourselves from React state. Trade-off: one extra re-render on
  // mouseenter/leave per bar; small enough to ignore.
  const [hoverCycle, setHoverCycle] = useState<number | null>(null)

  // When the matrix is present we trust its cycle list. Otherwise we
  // derive cycles from the data we have so the timeline still renders
  // for committees whose outflows don't trace to candidates.
  const cycles = useMemo(() => {
    if (matrix) return matrix.cycles
    const set = new Set<number>()
    for (const c of contributions) {
      const cy = cycleOf(c.contribution_date)
      if (cy !== null) set.add(cy)
    }
    for (const o of outgoing) {
      const cy = cycleOf(o.contribution_date)
      if (cy !== null) set.add(cy)
    }
    return Array.from(set).sort((a, b) => a - b)
  }, [matrix, contributions, outgoing])

  // Aggregate raw data per cycle once.
  const intakePerCycle = useMemo(() => {
    const m = new Map<number, number>()
    for (const c of contributions) {
      const cy = cycleOf(c.contribution_date)
      if (cy === null) continue
      m.set(cy, (m.get(cy) ?? 0) + c.amount)
    }
    return m
  }, [contributions])

  const outflowPerCycle = useMemo(() => {
    const m = new Map<number, number>()
    for (const o of outgoing) {
      const cy = cycleOf(o.contribution_date)
      if (cy === null) continue
      m.set(cy, (m.get(cy) ?? 0) + o.amount)
    }
    return m
  }, [outgoing])

  // Per-mode series.
  const bars: CycleBar[] = useMemo(() => {
    if (!selection) {
      // Page-level. When a matrix exists we lead with outflow per cycle
      // ("where this PAC moves money") since that's the matrix-eligible
      // series. Without a matrix the outflow doesn't trace to candidates
      // so we lead with intake instead. Reference = same value, so
      // share = 100% per cycle by definition.
      const series = matrix ? outflowPerCycle : intakePerCycle
      return cycles.map((cycle) => {
        const v = series.get(cycle) ?? 0
        return { cycle, selected: v, reference: v, share: v > 0 ? 1 : 0 }
      })
    }

    if (selection.kind === 'donor') {
      const perCycle = new Map<number, number>()
      for (const c of contributions) {
        if (c.donor_name !== selection.name) continue
        const cy = cycleOf(c.contribution_date)
        if (cy === null) continue
        perCycle.set(cy, (perCycle.get(cy) ?? 0) + c.amount)
      }
      return cycles.map((cycle) => {
        const sel = perCycle.get(cycle) ?? 0
        const ref = intakePerCycle.get(cycle) ?? 0
        return { cycle, selected: sel, reference: ref, share: ref > 0 ? sel / ref : 0 }
      })
    }

    if (selection.kind === 'candidate') {
      const perCycle = new Map<number, number>()
      for (const o of outgoing) {
        if (o.recipient_candidate_name !== selection.name) continue
        const cy = cycleOf(o.contribution_date)
        if (cy === null) continue
        perCycle.set(cy, (perCycle.get(cy) ?? 0) + o.amount)
      }
      return cycles.map((cycle) => {
        const sel = perCycle.get(cycle) ?? 0
        const ref = outflowPerCycle.get(cycle) ?? 0
        return { cycle, selected: sel, reference: ref, share: ref > 0 ? sel / ref : 0 }
      })
    }

    // Cell selection: replicate per-cycle proportional attribution for
    // this specific (donor, candidate) pair.
    const donorPerCycle = new Map<number, number>()
    for (const c of contributions) {
      if (c.donor_name !== selection.donor) continue
      const cy = cycleOf(c.contribution_date)
      if (cy === null) continue
      donorPerCycle.set(cy, (donorPerCycle.get(cy) ?? 0) + c.amount)
    }
    const candPerCycle = new Map<number, number>()
    for (const o of outgoing) {
      if (o.recipient_candidate_name !== selection.candidate) continue
      const cy = cycleOf(o.contribution_date)
      if (cy === null) continue
      candPerCycle.set(cy, (candPerCycle.get(cy) ?? 0) + o.amount)
    }
    return cycles.map((cycle) => {
      const intake = intakePerCycle.get(cycle) ?? 0
      const donorShare = intake > 0 ? (donorPerCycle.get(cycle) ?? 0) / intake : 0
      const candOut = candPerCycle.get(cycle) ?? 0
      const sel = donorShare * candOut
      const ref = outflowPerCycle.get(cycle) ?? 0
      return { cycle, selected: sel, reference: ref, share: ref > 0 ? sel / ref : 0 }
    })
  }, [selection, cycles, contributions, outgoing, intakePerCycle, outflowPerCycle])

  if (cycles.length === 0) return null

  // Layout
  const W = 480
  const H = 96
  const PAD_Y = 12
  const GAP = 8
  const barW = (W - GAP * (bars.length - 1)) / bars.length

  const maxValue =
    mode === 'dollars'
      ? Math.max(...bars.map((b) => b.selected), 1)
      : 1

  const headline = renderHeadline(bars, selection, pacDisplay, matrix !== null)
  // Page-level mode is the PAC's own outflow per cycle, so share is
  // 100% by definition. Toggle is only meaningful when something is
  // selected.
  const showShareToggle = selection !== null

  return (
    <section className="mb-6">
      <div className="border border-civic-navy/15 bg-civic-navy/[0.02] rounded-lg p-5 sm:p-6">
        <div className="flex items-baseline justify-between gap-4 flex-wrap mb-3">
          <div>
            <h2 className="text-xs font-semibold text-civic-navy uppercase tracking-widest">
              How this looks across cycles
            </h2>
            <p className="text-[14px] text-slate-700 leading-snug mt-1.5 max-w-prose">
              {headline}
            </p>
            {cycleFocus !== null ? (
              <p className="text-[12px] text-slate-500 mt-1.5">
                Showing only the <strong>{cycleFocus}</strong> cycle.{' '}
                <button
                  type="button"
                  onClick={() => onCycleFocus(null)}
                  className="text-civic-navy hover:underline underline-offset-2"
                >
                  Show all cycles
                </button>
              </p>
            ) : (
              <p className="text-[12px] text-slate-400 mt-1.5">
                Tip: click a bar to focus that cycle.
              </p>
            )}
          </div>
          {showShareToggle && (
            <div className="flex gap-1 bg-white border border-slate-200 rounded p-0.5 text-xs shrink-0">
              <button
                type="button"
                onClick={() => setMode('dollars')}
                className={`px-2.5 py-1 rounded ${
                  mode === 'dollars'
                    ? 'bg-civic-navy text-white'
                    : 'text-slate-500 hover:text-civic-navy'
                }`}
                aria-pressed={mode === 'dollars'}
              >
                Dollars
              </button>
              <button
                type="button"
                onClick={() => setMode('share')}
                className={`px-2.5 py-1 rounded ${
                  mode === 'share'
                    ? 'bg-civic-navy text-white'
                    : 'text-slate-500 hover:text-civic-navy'
                }`}
                aria-pressed={mode === 'share'}
              >
                Share of cycle
              </button>
            </div>
          )}
        </div>

        <svg
          viewBox={`0 0 ${W} ${H + 18}`}
          width="100%"
          height="auto"
          role="img"
          aria-label={`Per-cycle activity for ${cycles.length} election cycles`}
          className="overflow-visible max-w-[32rem]"
          preserveAspectRatio="xMinYMid meet"
        >
          {bars.map((b, i) => {
            const value = mode === 'dollars' ? b.selected : b.share
            const ratio = maxValue > 0 ? value / maxValue : 0
            const h = b.selected === 0 && b.reference === 0
              ? 1
              : Math.max(2, ratio * (H - PAD_Y))
            const x = i * (barW + GAP)
            const y = H - h
            const isEmpty = b.selected === 0
            const isFocused = cycleFocus === b.cycle
            const isHovered = hoverCycle === b.cycle && !isFocused
            const handleClick = () => {
              onCycleFocus(isFocused ? null : b.cycle)
            }
            // Persistent thin stroke on every bar so the chart reads as
            // a row of clickable tiles rather than a static image.
            // Hover and focus deepen the stroke; the active bar gets a
            // navy outline that wins on stacking order.
            const strokeColor = isFocused
              ? '#1e3a5f'
              : isHovered
                ? '#1e3a5f'
                : 'rgba(30, 58, 95, 0.22)'
            const strokeW = isFocused ? 2 : isHovered ? 2 : 1
            return (
              <g
                key={b.cycle}
                onClick={handleClick}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    handleClick()
                  }
                }}
                onMouseEnter={() => setHoverCycle(b.cycle)}
                onMouseLeave={() =>
                  setHoverCycle((c) => (c === b.cycle ? null : c))
                }
                role="button"
                tabIndex={0}
                aria-pressed={isFocused}
                aria-label={`${b.cycle} cycle: ${fmt(b.selected)}. ${
                  isFocused ? 'Clear focus.' : 'Focus this cycle.'
                }`}
                className="cursor-pointer focus:outline-none"
              >
                {/* Hit target spans the full bar column for easy click */}
                <rect
                  x={x - 2}
                  y={0}
                  width={barW + 4}
                  height={H + 18}
                  fill="transparent"
                />
                {/* Reference baseline track + persistent tile outline.
                    The track now spans the full chart height with a
                    visible outline so each bar's clickable area is
                    legible even when the bar value is small. */}
                <rect
                  x={x}
                  y={PAD_Y}
                  width={barW}
                  height={H - PAD_Y}
                  fill="rgba(30, 58, 95, 0.04)"
                  rx={2}
                  stroke={strokeColor}
                  strokeWidth={strokeW}
                  className="transition-all"
                />
                <rect
                  x={x}
                  y={y}
                  width={barW}
                  height={h}
                  fill={isEmpty ? '#cbd5e1' : '#d97706'}
                  rx={2}
                  opacity={isEmpty ? 0.3 : 1}
                  className="transition-all pointer-events-none"
                >
                  <title>
                    {b.cycle}: {fmt(b.selected)}
                    {b.reference > 0 && b.reference !== b.selected
                      ? ` (${pct(b.share)} of ${fmt(b.reference)} cycle total)`
                      : ''}
                    {isFocused ? ' — focused. Click to clear.' : ' — click to focus.'}
                  </title>
                </rect>
                <text
                  x={x + barW / 2}
                  y={H + 12}
                  textAnchor="middle"
                  fontSize={11}
                  fill={isFocused ? '#1e3a5f' : '#64748b'}
                  fontWeight={isFocused ? 700 : 500}
                  pointerEvents="none"
                >
                  {b.cycle}
                </text>
                {!isEmpty && (
                  <text
                    x={x + barW / 2}
                    y={Math.max(10, y - 3)}
                    textAnchor="middle"
                    fontSize={10}
                    fill="#1e3a5f"
                    fontWeight={600}
                    pointerEvents="none"
                  >
                    {mode === 'dollars' ? fmtShort(b.selected) : pct(b.share)}
                  </text>
                )}
              </g>
            )
          })}
        </svg>
      </div>
    </section>
  )
}

function renderHeadline(
  bars: CycleBar[],
  selection: Selection,
  pacDisplay: string,
  hasMatrix: boolean,
): React.ReactNode {
  const activeCycles = bars.filter((b) => b.selected > 0)
  if (activeCycles.length === 0) {
    return <>No tracked activity in this view across the cycles shown.</>
  }
  const top = activeCycles.reduce((a, b) => (a.selected > b.selected ? a : b))

  if (!selection) {
    const totalAcross = bars.reduce((s, b) => s + b.selected, 0)
    if (hasMatrix) {
      return (
        <>
          Across {bars.length} cycles, <strong>{pacDisplay}</strong> moved{' '}
          <strong>{fmt(totalAcross)}</strong> to other committees, peaking
          in <strong>{top.cycle}</strong>.
        </>
      )
    }
    return (
      <>
        Across {bars.length} cycles, <strong>{pacDisplay}</strong> raised{' '}
        <strong>{fmt(totalAcross)}</strong>, peaking in{' '}
        <strong>{top.cycle}</strong>.
      </>
    )
  }

  if (selection.kind === 'donor') {
    return (
      <>
        <strong>{selection.name}</strong> contributed to {pacDisplay} in{' '}
        <strong>{activeCycles.length}</strong> of the{' '}
        {bars.length} cycles shown, with the largest gift in{' '}
        <strong>{top.cycle}</strong> (<strong>{fmt(top.selected)}</strong>).
      </>
    )
  }

  if (selection.kind === 'candidate') {
    return (
      <>
        {pacDisplay}&apos;s flow to <strong>{selection.name}</strong>{' '}
        spans <strong>{activeCycles.length}</strong> cycle
        {activeCycles.length === 1 ? '' : 's'}, peaking in{' '}
        <strong>{top.cycle}</strong> (<strong>{fmt(top.selected)}</strong>).
      </>
    )
  }

  // cell
  return (
    <>
      Attributed conduit from <strong>{selection.donor}</strong> through{' '}
      {pacDisplay} to <strong>{selection.candidate}</strong> across{' '}
      <strong>{activeCycles.length}</strong> cycle
      {activeCycles.length === 1 ? '' : 's'}, largest in{' '}
      <strong>{top.cycle}</strong> (<strong>{fmt(top.selected)}</strong>).
    </>
  )
}
