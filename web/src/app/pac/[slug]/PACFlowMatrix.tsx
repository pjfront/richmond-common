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

function lastName(full: string): string {
  return full.trim().split(/\s+/).pop() ?? full
}

function shortDonor(name: string): string {
  if (name.length <= 28) return name
  return name.slice(0, 26).trim() + '…'
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
          Where the conduit runs
        </h2>
        <p className="text-[15px] text-slate-700 leading-[1.7] mb-5 max-w-prose">
          The grid below shows how money from{' '}
          <strong>{pacDisplay}</strong>&apos;s top donors flows through the
          committee to Richmond candidates across {cyclesLabel}. Rows are
          donors; columns are candidates. Click a row, column, or cell to
          filter the detail tables below. Total attributed:{' '}
          <strong>{fmtFull(total_attributed)}</strong>.
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
                      className="font-semibold text-center align-bottom pb-2 px-1 min-w-[68px] max-w-[80px]"
                    >
                      <button
                        type="button"
                        onClick={() => handleCandidateClick(c.name)}
                        className={`block w-full px-1 py-1 rounded text-[11px] leading-tight whitespace-nowrap transition-colors ${
                          isSelected
                            ? 'bg-civic-amber text-white'
                            : 'text-civic-navy hover:bg-civic-navy/10'
                        }`}
                        title={`Select ${c.name}`}
                      >
                        {lastName(c.name)}
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
                      className="text-left font-normal pr-2 py-1.5 sticky left-0 bg-white z-10 max-w-[210px]"
                    >
                      <button
                        type="button"
                        onClick={() => handleDonorClick(d.name)}
                        className={`block w-full text-left px-2 py-1 rounded transition-colors ${
                          isSelected
                            ? 'bg-civic-amber text-white'
                            : 'text-slate-700 hover:bg-civic-navy/5'
                        }`}
                        title={`Select ${d.name}`}
                      >
                        <div className="flex items-baseline justify-between gap-3">
                          <span
                            className="truncate text-[12px]"
                            title={d.name}
                          >
                            {shortDonor(d.name)}
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
                      const cellSelected = isCellSelected(d.name, c.name)
                      const cellDimmed = isCellDimmed(d.name, c.name)
                      return (
                        <td
                          key={c.name}
                          className="p-0"
                        >
                          <button
                            type="button"
                            disabled={isEmpty}
                            onClick={() =>
                              !isEmpty &&
                              handleCellClick(d.name, c.name, cell?.cycles ?? [])
                            }
                            className={`block w-full text-center tabular-nums px-1 py-1.5 rounded-sm text-[11px] transition-opacity ${
                              isEmpty ? 'cursor-default' : 'cursor-pointer hover:opacity-90'
                            } ${cellSelected ? 'ring-2 ring-civic-amber' : ''} ${
                              cellDimmed && !isEmpty ? 'opacity-40' : ''
                            }`}
                            style={{
                              backgroundColor: bg(amount),
                              color: fg(amount),
                            }}
                            title={
                              isEmpty
                                ? `${d.name} → ${c.name}: no attributed flow`
                                : `${d.name} → ${c.name}: ${fmtFull(
                                    amount,
                                  )} (cycles ${cell?.cycles.join(', ')})`
                            }
                            aria-label={
                              isEmpty
                                ? `${d.name} contributed nothing to ${c.name} via this PAC`
                                : `${d.name} contributed ${fmtFull(
                                    amount,
                                  )} to ${c.name} via this PAC. Click to filter.`
                            }
                          >
                            {isEmpty ? '·' : fmtShort(amount)}
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

        <details className="mt-5 text-[12px] text-slate-500 leading-relaxed">
          <summary className="cursor-pointer font-semibold text-slate-600 hover:text-civic-navy">
            How this is computed
          </summary>
          <div className="mt-2 space-y-2 max-w-prose">
            <p>
              PACs are pooled funds, so a specific incoming dollar cannot
              be tied to a specific outgoing dollar. The matrix shows
              <strong> proportional attribution</strong>: for each
              election cycle, each donor&apos;s share of the PAC&apos;s
              intake is applied to each outgoing flow to a candidate that
              cycle. A donor giving 25 percent of the PAC&apos;s 2024
              intake is credited with 25 percent of each 2024 outflow.
              Cell amounts sum across cycles.
            </p>
            <p>
              This is the honest middle ground. It respects the temporal
              beat of campaign finance (money raised in 2018 funded
              2018&ndash;2020 outflows, not 2024 races) without
              overclaiming an attribution the data cannot support. The
              detail tables below show the underlying contributions and
              outflows without attribution.
            </p>
          </div>
        </details>
      </div>
    </section>
  )
}
