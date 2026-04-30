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

export type Selection =
  | { kind: 'donor'; name: string }
  | { kind: 'candidate'; name: string }
  | { kind: 'cell'; donor: string; candidate: string; cycles: number[] }
  | null

interface Props {
  matrix: PACFlowMatrixData
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

export default function PACProfileDashboard({
  matrix,
  contributions,
  outgoing,
  pacDisplay,
}: Props) {
  const [selection, setSelection] = useState<Selection>(null)

  const filteredContributions = useMemo(() => {
    if (!selection) return contributions
    if (selection.kind === 'donor') {
      return contributions.filter((c) => c.donor_name === selection.name)
    }
    if (selection.kind === 'cell') {
      return contributions.filter(
        (c) =>
          c.donor_name === selection.donor &&
          selection.cycles.some((y) => inCycle(c.contribution_date, y)),
      )
    }
    return contributions
  }, [contributions, selection])

  const filteredOutgoing = useMemo(() => {
    if (!selection) return outgoing
    if (selection.kind === 'candidate') {
      return outgoing.filter(
        (o) => o.recipient_candidate_name === selection.name,
      )
    }
    if (selection.kind === 'cell') {
      return outgoing.filter(
        (o) =>
          o.recipient_candidate_name === selection.candidate &&
          selection.cycles.some((y) => inCycle(o.contribution_date, y)),
      )
    }
    return outgoing
  }, [outgoing, selection])

  const contextStrip = renderContextStrip(selection, matrix, pacDisplay)

  return (
    <>
      <PACFlowMatrix
        matrix={matrix}
        pacDisplay={pacDisplay}
        selection={selection}
        onSelect={setSelection}
      />

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
        across <strong>{contributions.length}</strong> filing
        {contributions.length === 1 ? '' : 's'}.
      </>
    )
  }
  return (
    <>
      Donations to <strong>{pacDisplay}</strong> across{' '}
      <strong>{contributions.length}</strong> contribution
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
        <strong>{outgoing.length}</strong> filing
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
