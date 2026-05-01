'use client'

/**
 * PACProfileDashboard. Owns the selection state for the Explore-then-
 * detail interaction on PAC profile pages (Phase 2 of V2).
 *
 * Wraps the matrix and the two detail tables. When a donor row,
 * candidate column, or specific cell is selected in the matrix, the
 * tables below are filtered accordingly:
 *   - donor selected: donor table reduces to that donor's contributions;
 *     outgoing table is unchanged.
 *   - candidate selected: outgoing table reduces to that candidate's
 *     receiving committee filings; donor table is unchanged.
 *   - cell selected: BOTH tables reduce, AND restricted to the cycles
 *     in which the cell's attributed flow occurred.
 *
 * The selection state is intentionally local to this component. Hero,
 * lede, and footer remain server-rendered above and below the dashboard
 * in [slug]/page.tsx.
 */

import { useMemo, useState } from 'react'
import type { PACFlowMatrix as PACFlowMatrixData } from '@/lib/queries'
import type { PACContributionRow, PACOutgoingRow } from '@/lib/types'
import PACFlowMatrix from './PACFlowMatrix'
import PACDonorTable from './PACDonorTable'
import PACOutgoingTable from './PACOutgoingTable'
import CycleBarsTimeline from './CycleBarsTimeline'

export type Selection =
  | { kind: 'donor'; name: string }
  | { kind: 'candidate'; name: string }
  | { kind: 'cell'; donor: string; candidate: string; cycles: number[] }
  | null

interface Props {
  /** Matrix is optional. When null we still render the cycle-bars
   *  timeline and the receipt tables, just without the donor-x-candidate
   *  flow grid above them. This unifies the page template across PACs
   *  whose outflows trace to candidates and PACs whose outflows go to
   *  other committees. */
  matrix: PACFlowMatrixData | null
  contributions: PACContributionRow[]
  outgoing: PACOutgoingRow[]
  pacDisplay: string
}

function fmt(n: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(n)
}

function inCycle(dateIso: string, cycle: number): boolean {
  // Bucketing matches the matrix: even years stay; odd years roll
  // forward to the next even year.
  const year = parseInt(dateIso.slice(0, 4), 10)
  if (Number.isNaN(year)) return false
  const bucket = year % 2 === 0 ? year : year + 1
  return bucket === cycle
}

type CycleScope = 'current' | 'last2' | 'all'

function cycleOfDate(dateIso: string): number | null {
  const y = parseInt(dateIso.slice(0, 4), 10)
  if (Number.isNaN(y)) return null
  return y % 2 === 0 ? y : y + 1
}

export default function PACProfileDashboard({
  matrix,
  contributions,
  outgoing,
  pacDisplay,
}: Props) {
  const [selection, setSelection] = useState<Selection>(null)

  // Cycle scope is the page-level temporal control. Default to current
  // cycle (the relevant election) so the matrix and tables aren't
  // dominated by ten-year-old data on first load. The bars timeline
  // ALWAYS shows the full history regardless — it's the navigation
  // surface that lets the reader expand scope without a chip click.
  const currentCycle = useMemo(() => {
    const y = new Date().getFullYear()
    return y % 2 === 0 ? y : y + 1
  }, [])
  const [cycleScope, setCycleScope] = useState<CycleScope>('current')
  // cycleFocus is set when the user clicks a single bar in the timeline.
  // It overrides cycleScope — a bar click is a finer-grained "show me
  // just this cycle" intent than the chip-controlled band. Click the
  // same bar again (or any chip) to clear.
  const [cycleFocus, setCycleFocus] = useState<number | null>(null)
  const activeCycles = useMemo(() => {
    if (cycleFocus !== null) return new Set([cycleFocus])
    if (cycleScope === 'all') return null
    if (cycleScope === 'last2') return new Set([currentCycle - 2, currentCycle])
    return new Set([currentCycle])
  }, [cycleScope, cycleFocus, currentCycle])

  // Apply cycle scope FIRST, then per-selection narrowing.
  const inScopeContributions = useMemo(() => {
    if (!activeCycles) return contributions
    return contributions.filter((c) => {
      const cy = cycleOfDate(c.contribution_date)
      return cy !== null && activeCycles.has(cy)
    })
  }, [contributions, activeCycles])

  const inScopeOutgoing = useMemo(() => {
    if (!activeCycles) return outgoing
    return outgoing.filter((o) => {
      const cy = cycleOfDate(o.contribution_date)
      return cy !== null && activeCycles.has(cy)
    })
  }, [outgoing, activeCycles])

  // Matrix cells filter: keep cells whose `cycles` array intersects
  // the active scope. Drop donors whose remaining attributed flow is
  // tiny — that's the "individuals listed" cleanup. Threshold is
  // amount-based, not type-based, since we don't classify donors
  // (organization vs individual) at ingestion.
  const inScopeMatrix = useMemo<PACFlowMatrixData | null>(() => {
    if (!matrix) return null
    if (!activeCycles) return matrix
    const filteredCells = matrix.cells
      .map((c) => {
        const overlap = c.cycles.filter((y) => activeCycles.has(y))
        if (overlap.length === 0) return null
        // Approximate by-cycle amount. Per-cycle precision would
        // require server-side breakdown; this is good enough for
        // the matrix's purpose (relative magnitude across donor x
        // candidate within a scope).
        const ratio = overlap.length / c.cycles.length
        return {
          donor_name: c.donor_name,
          candidate_name: c.candidate_name,
          cycles: overlap,
          amount: c.amount * ratio,
        }
      })
      .filter((c): c is PACFlowMatrixData['cells'][number] => c !== null)
    if (filteredCells.length === 0) return null
    const donorTotals = new Map<string, number>()
    const candidateTotals = new Map<string, number>()
    for (const c of filteredCells) {
      donorTotals.set(
        c.donor_name,
        (donorTotals.get(c.donor_name) ?? 0) + c.amount,
      )
      candidateTotals.set(
        c.candidate_name,
        (candidateTotals.get(c.candidate_name) ?? 0) + c.amount,
      )
    }
    // Drop donors below threshold; this trims the "individual donors
    // listed for $9 each" noise that dominates RPOA's grid when shown
    // at full scope.
    const DONOR_FLOOR = 250
    const visibleDonors = matrix.donors
      .map((d) => ({ ...d, total_attributed: donorTotals.get(d.name) ?? 0 }))
      .filter((d) => d.total_attributed >= DONOR_FLOOR)
      .sort((a, b) => b.total_attributed - a.total_attributed)
    const visibleCandidates = matrix.candidates
      .map((c) => ({
        ...c,
        total_received_via_pac: candidateTotals.get(c.name) ?? 0,
      }))
      .filter((c) => c.total_received_via_pac > 0)
      .sort((a, b) => b.total_received_via_pac - a.total_received_via_pac)
    if (visibleDonors.length === 0 || visibleCandidates.length === 0) {
      return null
    }
    const visibleDonorNames = new Set(visibleDonors.map((d) => d.name))
    const visibleCandidateNames = new Set(visibleCandidates.map((c) => c.name))
    const finalCells = filteredCells.filter(
      (c) =>
        visibleDonorNames.has(c.donor_name) &&
        visibleCandidateNames.has(c.candidate_name),
    )
    const total = finalCells.reduce((s, c) => s + c.amount, 0)
    return {
      donors: visibleDonors,
      candidates: visibleCandidates,
      cells: finalCells,
      total_attributed: total,
      cycles: Array.from(activeCycles).sort((a, b) => a - b),
    }
  }, [matrix, activeCycles])

  const filteredContributions = useMemo(() => {
    if (!selection) return inScopeContributions
    if (selection.kind === 'donor') {
      return inScopeContributions.filter((c) => c.donor_name === selection.name)
    }
    if (selection.kind === 'cell') {
      return inScopeContributions.filter(
        (c) =>
          c.donor_name === selection.donor &&
          selection.cycles.some((y) => inCycle(c.contribution_date, y)),
      )
    }
    return inScopeContributions
  }, [inScopeContributions, selection])

  const filteredOutgoing = useMemo(() => {
    if (!selection) return inScopeOutgoing
    if (selection.kind === 'candidate') {
      return inScopeOutgoing.filter(
        (o) => o.recipient_candidate_name === selection.name,
      )
    }
    if (selection.kind === 'cell') {
      return inScopeOutgoing.filter(
        (o) =>
          o.recipient_candidate_name === selection.candidate &&
          selection.cycles.some((y) => inCycle(o.contribution_date, y)),
      )
    }
    return inScopeOutgoing
  }, [inScopeOutgoing, selection])

  const contextStrip = inScopeMatrix
    ? renderContextStrip(selection, inScopeMatrix, pacDisplay)
    : null

  const scopeLabels: Record<CycleScope, string> = {
    current: `${currentCycle} cycle`,
    last2: `${currentCycle - 2}–${currentCycle}`,
    all: 'All time',
  }
  const scopeSubLabels: Record<CycleScope, string> = {
    current: 'This election',
    last2: 'Last two cycles',
    all: 'Lifetime',
  }

  return (
    <>
      {/* Scope chips. Same shape as the index page's temporal control,
          carried into the profile so reader's mental model is preserved. */}
      <div className="mb-5">
        <div className="flex flex-wrap items-stretch gap-2">
          {(['current', 'last2', 'all'] as CycleScope[]).map((s) => {
            // When a single bar is focused, no chip is "active" —
            // the active filter is the bar itself. Click any chip to
            // clear the focus.
            const active = cycleFocus === null && cycleScope === s
            return (
              <button
                key={s}
                type="button"
                onClick={() => {
                  setCycleScope(s)
                  setCycleFocus(null)
                  setSelection(null)
                }}
                aria-pressed={active}
                className={`group flex flex-col items-start text-left rounded-lg px-4 py-2.5 border transition-all ${
                  active
                    ? 'bg-civic-amber border-civic-amber text-white shadow-sm'
                    : 'bg-white border-slate-200 text-slate-700 hover:border-civic-amber/60 hover:bg-civic-amber/[0.04]'
                }`}
              >
                <span className="text-sm font-semibold tabular-nums">
                  {scopeLabels[s]}
                </span>
                <span
                  className={`text-[11px] leading-tight mt-0.5 ${
                    active
                      ? 'text-white/85'
                      : 'text-slate-500 group-hover:text-slate-600'
                  }`}
                >
                  {scopeSubLabels[s]}
                </span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Temporal layer first — always rendered. The bars use the FULL
          history (not in-scope data) so the reader can see the cycle
          context regardless of the active chip. Bar clicks set
          cycleFocus, overriding the chip band. */}
      <CycleBarsTimeline
        matrix={matrix}
        contributions={contributions}
        outgoing={outgoing}
        pacDisplay={pacDisplay}
        selection={selection}
        cycleFocus={cycleFocus}
        onCycleFocus={(c) => {
          setCycleFocus(c)
          setSelection(null)
        }}
      />

      {/* Conduit grid. Filtered by scope; hidden entirely when no
          attributed flow remains in-scope (e.g. ballot-measure
          committees in the current cycle). */}
      {inScopeMatrix && (
        <PACFlowMatrix
          matrix={inScopeMatrix}
          pacDisplay={pacDisplay}
          selection={selection}
          onSelect={setSelection}
        />
      )}

      {inScopeMatrix && (
        <div
          className={`mb-6 rounded-lg border px-4 py-3 transition-colors ${
            selection
              ? 'border-civic-amber/50 bg-civic-amber/5'
              : 'border-slate-200 bg-slate-50'
          }`}
          aria-live="polite"
        >
          <div className="flex items-center justify-between flex-wrap gap-3">
            <p className="text-sm text-slate-700">{contextStrip}</p>
            {selection && (
              <button
                type="button"
                onClick={() => setSelection(null)}
                className="text-xs font-medium text-civic-navy hover:text-civic-navy-light underline-offset-2 hover:underline"
              >
                Show all ×
              </button>
            )}
          </div>
        </div>
      )}

      {filteredContributions.length > 0 ? (
        <section className="mb-6">
          <div className="border-l-4 border-civic-amber/60 bg-civic-amber/[0.03] rounded-r-lg p-5 sm:p-6">
            <h2 className="text-xs font-semibold text-civic-amber uppercase tracking-widest mb-3">
              Where the money came from
            </h2>
            <p className="text-[15px] text-slate-700 leading-[1.8] mb-4">
              {renderInflowNarrative(
                filteredContributions,
                pacDisplay,
                selection,
              )}
            </p>
            <PACDonorTable contributions={filteredContributions} />
          </div>
        </section>
      ) : (
        <section className="mb-6">
          <div className="border border-slate-200 rounded-lg p-5 sm:p-6 text-center">
            <p className="text-sm text-slate-500 italic">
              No contributions match the current selection.
            </p>
          </div>
        </section>
      )}

      {filteredOutgoing.length > 0 ? (
        <section className="mb-6">
          <div className="border border-slate-200 rounded-lg p-5 sm:p-6">
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-3">
              Where the money went
            </h2>
            <p className="text-[15px] text-slate-700 leading-[1.8] mb-4">
              {renderOutflowNarrative(filteredOutgoing, pacDisplay, selection)}
            </p>
            <PACOutgoingTable outgoing={filteredOutgoing} />
            <p className="text-xs text-slate-400 mt-4 pt-3 border-t border-slate-100 leading-relaxed">
              These rows come from other committees&apos; filings that listed
              this committee as a donor. Name matching is loose
              (committee&nbsp;name → donor&nbsp;name on another filing), so
              review for unrelated committees that share a name fragment.
            </p>
          </div>
        </section>
      ) : (
        selection && (
          <section className="mb-6">
            <div className="border border-slate-200 rounded-lg p-5 sm:p-6 text-center">
              <p className="text-sm text-slate-500 italic">
                No outgoing flows match the current selection.
              </p>
            </div>
          </section>
        )
      )}
    </>
  )
}

function renderContextStrip(
  selection: Selection,
  matrix: PACFlowMatrixData,
  pacDisplay: string,
): React.ReactNode {
  if (!selection) {
    return (
      <>
        <span className="font-medium">Tip:</span> Click a row, column, or
        cell in the grid above to filter the detail tables below.
      </>
    )
  }

  if (selection.kind === 'donor') {
    const donor = matrix.donors.find((d) => d.name === selection.name)
    return (
      <>
        <span className="text-slate-500">Showing all contributions from</span>{' '}
        <span className="font-semibold text-civic-navy">
          {selection.name}
        </span>
        {donor && (
          <span className="text-slate-500">
            , attributed share to candidates via {pacDisplay}:{' '}
            <span className="font-semibold text-slate-800 tabular-nums">
              {fmt(donor.total_attributed)}
            </span>
          </span>
        )}
      </>
    )
  }

  if (selection.kind === 'candidate') {
    const cand = matrix.candidates.find((c) => c.name === selection.name)
    return (
      <>
        <span className="text-slate-500">Showing flows from {pacDisplay} to</span>{' '}
        <span className="font-semibold text-civic-navy">
          {selection.name}
        </span>
        {cand && (
          <span className="text-slate-500">
            , total via this committee:{' '}
            <span className="font-semibold text-slate-800 tabular-nums">
              {fmt(cand.total_received_via_pac)}
            </span>
          </span>
        )}
      </>
    )
  }

  // cell
  const cell = matrix.cells.find(
    (c) =>
      c.donor_name === selection.donor &&
      c.candidate_name === selection.candidate,
  )
  const cycles = selection.cycles
  const cyclesText =
    cycles.length === 1
      ? `the ${cycles[0]} cycle`
      : cycles.length === 2
        ? `the ${cycles[0]} and ${cycles[1]} cycles`
        : `cycles ${cycles.join(', ')}`
  return (
    <>
      <span className="text-slate-500">Showing the conduit from</span>{' '}
      <span className="font-semibold text-civic-navy">{selection.donor}</span>{' '}
      <span className="text-slate-500">through {pacDisplay} to</span>{' '}
      <span className="font-semibold text-civic-navy">
        {selection.candidate}
      </span>
      {cell && (
        <span className="text-slate-500">
          , attributed{' '}
          <span className="font-semibold text-slate-800 tabular-nums">
            {fmt(cell.amount)}
          </span>{' '}
          across {cyclesText}
        </span>
      )}
    </>
  )
}

function renderInflowNarrative(
  contributions: PACContributionRow[],
  pacDisplay: string,
  selection: Selection,
): React.ReactNode {
  if (selection?.kind === 'donor' || selection?.kind === 'cell') {
    return (
      <>
        Contributions to <strong>{pacDisplay}</strong> from this donor
        across <strong>{contributions.length.toLocaleString()}</strong> filing
        {contributions.length === 1 ? '' : 's'}.
      </>
    )
  }
  return (
    <>
      Donations to <strong>{pacDisplay}</strong> across{' '}
      <strong>{contributions.length.toLocaleString()}</strong> contribution
      {contributions.length === 1 ? '' : 's'}. Sortable by donor or amount;
      search by name or employer.
    </>
  )
}

function renderOutflowNarrative(
  outgoing: PACOutgoingRow[],
  pacDisplay: string,
  selection: Selection,
): React.ReactNode {
  const total = outgoing.reduce((s, o) => s + o.amount, 0)
  const recipients = new Set(outgoing.map((o) => o.recipient_committee_name)).size

  if (selection?.kind === 'candidate' || selection?.kind === 'cell') {
    return (
      <>
        <strong>{pacDisplay}</strong> appears as a donor on{' '}
        <strong>{outgoing.length.toLocaleString()}</strong> filing
        {outgoing.length === 1 ? '' : 's'} to this candidate&apos;s
        committee, totaling <strong>{fmt(total)}</strong>.
      </>
    )
  }
  return (
    <>
      <strong>{pacDisplay}</strong> appears as a donor on filings for{' '}
      <strong>{recipients}</strong> other committee
      {recipients === 1 ? '' : 's'}, totaling{' '}
      <strong>{fmt(total)}</strong>.
    </>
  )
}
