'use client'

/**
 * PACFlowMatrix. Donors x candidates conduit grid for PAC profile pages.
 *
 * Rows = top donors to this PAC by proportionally-attributed dollar
 * flow to candidates. Columns = candidates this PAC has supported.
 * Cells = the donor's attributed share of PAC outflows to that
 * candidate, in dollars.
 *
 * Methodology (the "How this is computed" caveat is shown inline below):
 * proportional attribution per cycle. If a donor gave 5 percent of the
 * PAC's intake in 2024, they are credited with 5 percent of each
 * outgoing dollar that PAC sent to a candidate in 2024. Summed across
 * cycles. PACs are pooled funds, so this is necessarily approximate.
 *
 * Selection: click a row header to select a donor, a column header to
 * select a candidate, or a cell to select a (donor, candidate) pair.
 * The parent dashboard uses the selection to filter the detail tables
 * below. Click an active selection again to clear it.
 */

import type { PACFlowMatrix as PACFlowMatrixData } from '@/lib/queries'
import type { Selection } from './PACProfileDashboard'

interface Props {
  matrix: PACFlowMatrixData
  pacDisplay: string
  selection: Selection
  onSelect: (next: Selection) => void
}

function fmtShort(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`
  if (n >= 10_000) return `$${Math.round(n / 1000)}k`
  if (n >= 1_000) return `$${(n / 1000).toFixed(1)}k`
  return `$${Math.round(n)}`
}

function fmtFull(n: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(n)
}

/** Short display name for a candidate column header. Uses first name +
 *  last name when it fits, falls back to first initial + last name. */
function shortCandidate(full: string): string {
  const parts = full.trim().split(/\s+/)
  if (parts.length < 2) return full
  const first = parts[0]
  const last = parts[parts.length - 1]
  // If first name is short enough, show it in full
  const combo = `${first} ${last}`
  if (combo.length <= 16) return combo
  // Otherwise use initial
  return `${first[0]}. ${last}`
}

function selectionHint(
  selection: Selection,
  pacDisplay: string,
): string {
  if (!selection) {
    return `Click a donor name to filter the "Where the money came from" table below. Click a candidate name to filter "Where the money went." Click a dollar amount to see the specific flow from one donor to one candidate.`
  }
  if (selection.kind === 'donor') {
    return `Showing contributions from ${selection.name}. Click a dollar amount in their row to see which candidates their money reached.`
  }
  if (selection.kind === 'candidate') {
    return `Showing flows to ${selection.name}. Click a dollar amount in their column to trace it back to a specific donor.`
  }
  // cell
  const cycleText =
    selection.cycles.length === 1
      ? `the ${selection.cycles[0]} cycle`
      : `cycles ${selection.cycles.join(', ')}`
  return `Showing the flow from ${selection.donor} to ${selection.candidate} across ${cycleText}. Both tables below are filtered to this connection.`
}

export default function PACFlowMatrix({ matrix, pacDisplay, selection, onSelect }: Props) {
  const { donors, candidates, cells, total_attributed, cycles } = matrix

  const cellByDonorCandidate = new Map<string, Map<string, { amount: number; cycles: number[] }>>()
  for (const c of cells) {
    let perDonor = cellByDonorCandidate.get(c.donor_name)
    if (!perDonor) {
      perDonor = new Map()
      cellByDonorCandidate.set(c.donor_name, perDonor)
    }
    perDonor.set(c.candidate_name, { amount: c.amount, cycles: c.cycles })
  }

  const maxAmount = Math.max(...cells.map((c) => c.amount), 1)
  function bg(amount: number): string {
    if (amount <= 0) return 'transparent'
    const ratio = Math.log10(amount + 1) / Math.log10(maxAmount + 1)
    const opacity = 0.08 + ratio * 0.85
    return `rgba(217, 119, 6, ${opacity.toFixed(2)})`
  }
  function fg(amount: number): string {
    if (amount <= 0) return '#cbd5e1'
    const ratio = Math.log10(amount + 1) / Math.log10(maxAmount + 1)
    return ratio > 0.55 ? '#ffffff' : '#1e3a5f'
  }

  const cyclesLabel =
    cycles.length === 1
      ? `the ${cycles[0]} cycle`
      : `the ${cycles[0]}–${cycles[cycles.length - 1]} cycles`

  // Selection helpers
  const selDonor =
    selection?.kind === 'donor'
      ? selection.name
      : selection?.kind === 'cell'
        ? selection.donor
        : null
  const selCandidate =
    selection?.kind === 'candidate'
      ? selection.name
      : selection?.kind === 'cell'
        ? selection.candidate
        : null

  function isCellSelected(donor: string, candidate: string): boolean {
    if (!selection) return false
    if (selection.kind === 'cell')
      return selection.donor === donor && selection.candidate === candidate
    if (selection.kind === 'donor') return selection.name === donor
    if (selection.kind === 'candidate') return selection.name === candidate
    return false
  }

  function isCellDimmed(donor: string, candidate: string): boolean {
    if (!selection) return false
    return !isCellSelected(donor, candidate)
  }

  function handleDonorClick(name: string) {
    if (selection?.kind === 'donor' && selection.name === name) onSelect(null)
    else onSelect({ kind: 'donor', name })
  }
  function handleCandidateClick(name: string) {
    if (selection?.kind === 'candidate' && selection.name === name) onSelect(null)
    else onSelect({ kind: 'candidate', name })
  }
  function handleCellClick(donor: string, candidate: string, cellCycles: number[]) {
    if (
      selection?.kind === 'cell' &&
      selection.donor === donor &&
      selection.candidate === candidate
    ) {
      onSelect(null)
    } else {
      onSelect({ kind: 'cell', donor, candidate, cycles: cellCycles })
    }
  }

  return (
    <section className="mb-8">
      <div className="border border-civic-navy/15 bg-white rounded-lg p-5 sm:p-6">
        <h2 className="text-xs font-semibold text-civic-navy uppercase tracking-widest mb-1">
          How donor money reaches candidates
        </h2>
        <p className="text-[15px] text-slate-700 leading-[1.7] mb-5 max-w-prose">
          Where did <strong>{pacDisplay}</strong>&apos;s donors&apos; money
          end up? Each row is a donor, each column is a candidate. The
          dollar amounts in the grid are estimates — a donor who gave 25%
          of the committee&apos;s money in a cycle is counted as funding
          25% of each candidate the committee supported that cycle. This is
          approximate because campaign funds are pooled. Click any amount
          to see the underlying filings.
        </p>

        <div className="overflow-x-auto">
          <table className="border-separate border-spacing-1 text-xs">
            <thead>
              <tr>
                <th
                  scope="col"
                  className="text-left font-medium text-slate-400 align-bottom pr-2 pb-2 sticky left-0 bg-white z-10"
                >
                  <span className="text-[10px] uppercase tracking-wider">Donor &rarr;</span>
                </th>
                {candidates.map((c) => {
                  const isSelected = selCandidate === c.name
                  return (
                    <th
                      key={c.name}
                      scope="col"
                      className="font-semibold text-center align-bottom pb-2 px-1 min-w-[72px] max-w-[96px]"
                    >
                      <button
                        type="button"
                        onClick={() => handleCandidateClick(c.name)}
                        className={`block w-full px-1 py-1 rounded text-[11px] leading-tight transition-colors ${
                          isSelected
                            ? 'bg-civic-amber text-white'
                            : 'text-civic-navy hover:bg-civic-navy/10'
                        }`}
                        title={c.name}
                      >
                        {shortCandidate(c.name)}
                      </button>
                      <div className="text-[10px] text-slate-400 tabular-nums mt-0.5">
                        {fmtShort(c.total_received_via_pac)}
                      </div>
                    </th>
                  )
                })}
              </tr>
            </thead>
            <tbody>
              {donors.map((d) => {
                const perDonor = cellByDonorCandidate.get(d.name)
                const isSelected = selDonor === d.name
                return (
                  <tr key={d.name}>
                    <th
                      scope="row"
                      className="text-left font-normal pr-2 py-1.5 sticky left-0 bg-white z-10 max-w-[260px]"
                    >
                      <button
                        type="button"
                        onClick={() => handleDonorClick(d.name)}
                        className={`block w-full text-left px-2 py-1 rounded transition-colors ${
                          isSelected
                            ? 'bg-civic-amber text-white'
                            : 'text-slate-700 hover:bg-civic-navy/5'
                        }`}
                        title={d.name}
                      >
                        <div className="flex items-baseline justify-between gap-3">
                          <span
                            className="truncate text-[12px]"
                            title={d.name}
                          >
                            {d.name}
                          </span>
                          <span
                            className={`text-[10px] tabular-nums shrink-0 ${
                              isSelected ? 'text-white/85' : 'text-slate-400'
                            }`}
                          >
                            {fmtShort(d.total_attributed)}
                          </span>
                        </div>
                      </button>
                    </th>
                    {candidates.map((c) => {
                      const cell = perDonor?.get(c.name)
                      const amount = cell?.amount ?? 0
                      const isEmpty = amount <= 0
                      if (isEmpty) {
                        // Empty cells render as bare table cells. The
                        // earlier grey-track approach made the grid
                        // feel mostly-empty; sparse rendering lets the
                        // eye settle on the actual flow.
                        return (
                          <td
                            key={c.name}
                            className="p-0 text-center text-slate-200 text-[11px]"
                            aria-hidden="true"
                          >
                            <span className="block px-1 py-1.5">·</span>
                          </td>
                        )
                      }
                      const cellSelected = isCellSelected(d.name, c.name)
                      const cellDimmed = isCellDimmed(d.name, c.name)
                      return (
                        <td
                          key={c.name}
                          className="p-0"
                        >
                          <button
                            type="button"
                            onClick={() =>
                              handleCellClick(d.name, c.name, cell?.cycles ?? [])
                            }
                            className={`block w-full text-center tabular-nums px-1 py-1.5 rounded-sm text-[11px] transition-opacity cursor-pointer hover:opacity-90 ${
                              cellSelected ? 'ring-2 ring-civic-amber' : ''
                            } ${cellDimmed ? 'opacity-40' : ''}`}
                            style={{
                              backgroundColor: bg(amount),
                              color: fg(amount),
                            }}
                            title={`${d.name} → ${c.name}: ${fmtFull(
                              amount,
                            )} (cycles ${cell?.cycles.join(', ')})`}
                            aria-label={`${d.name} contributed ${fmtFull(
                              amount,
                            )} to ${c.name} via this PAC. Click to filter.`}
                          >
                            {fmtShort(amount)}
                          </button>
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {/* Selection hint — changes based on what the user clicked */}
        <div
          className={`mt-4 rounded-md px-3 py-2 text-[12px] leading-relaxed transition-colors ${
            selection
              ? 'border border-civic-amber/40 bg-civic-amber/[0.04] text-slate-700'
              : 'border border-slate-200 bg-slate-50 text-slate-500'
          }`}
          aria-live="polite"
        >
          {selectionHint(selection, pacDisplay)}
        </div>

        <details className="mt-5 text-[12px] text-slate-500 leading-relaxed">
          <summary className="cursor-pointer font-semibold text-slate-600 hover:text-civic-navy">
            How this is computed
          </summary>
          <div className="mt-2 space-y-2 max-w-prose">
            <p>
              Campaign committees pool donations together, so we
              can&apos;t say &ldquo;this specific dollar went to this
              specific candidate.&rdquo; Instead, we estimate: for
              each two-year election cycle, if a donor gave 25% of the
              committee&apos;s total money that cycle, we count them
              as funding 25% of every dollar the committee gave to
              candidates that same cycle. Dollar amounts in the grid
              add up across cycles.
            </p>
            <p>
              This respects the timing of campaign finance — money
              raised in 2018 funded 2018–2020 races, not 2024
              races — without claiming precision the data
              can&apos;t support. The tables below show the actual
              contribution and spending records without any
              estimation.
            </p>
          </div>
        </details>
      </div>
    </section>
  )
}
