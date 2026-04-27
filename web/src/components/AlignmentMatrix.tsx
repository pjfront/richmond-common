'use client'

import { useMemo, useState } from 'react'
import type { PairwiseAlignment } from '@/lib/types'
import { formatCategory } from '@/components/CategoryBadge'

export interface SelectedPair {
  aId: string
  aName: string
  bId: string
  bName: string
}

interface AlignmentMatrixProps {
  alignments: PairwiseAlignment[]
  officials: Array<{ id: string; name: string }>
  categories: string[]
  selectedPair: SelectedPair | null
  onPairSelect: (pair: SelectedPair | null) => void
}

function lastName(name: string): string {
  const parts = name.trim().split(/\s+/)
  return parts[parts.length - 1]
}

function pairKey(idA: string, idB: string): string {
  const [first, second] = idA < idB ? [idA, idB] : [idB, idA]
  return `${first}|${second}`
}

function cellTone(rate: number, votes: number): string {
  // Disagreement is the interesting signal — saturate the low end.
  if (votes < 5) return 'bg-slate-50 text-slate-400 ring-slate-100'
  if (rate >= 0.85) return 'bg-emerald-200/70 text-emerald-900 ring-emerald-300'
  if (rate >= 0.70) return 'bg-emerald-100 text-emerald-800 ring-emerald-200'
  if (rate >= 0.55) return 'bg-amber-100 text-amber-900 ring-amber-200'
  if (rate >= 0.40) return 'bg-orange-200/80 text-orange-900 ring-orange-300'
  return 'bg-rose-300/80 text-rose-950 ring-rose-400'
}

export default function AlignmentMatrix({
  alignments,
  officials,
  categories,
  selectedPair,
  onPairSelect,
}: AlignmentMatrixProps) {
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)

  const pairLookup = useMemo(() => {
    const map = new Map<string, PairwiseAlignment>()
    for (const a of alignments) {
      if (a.category === selectedCategory) {
        map.set(pairKey(a.official_a_id, a.official_b_id), a)
      }
    }
    return map
  }, [alignments, selectedCategory])

  const getAlignment = (idA: string, idB: string) =>
    pairLookup.get(pairKey(idA, idB))

  const selectedKey = selectedPair
    ? pairKey(selectedPair.aId, selectedPair.bId)
    : null

  function handleCellClick(row: { id: string; name: string }, col: { id: string; name: string }) {
    if (row.id === col.id) return
    const key = pairKey(row.id, col.id)
    if (key === selectedKey) {
      onPairSelect(null)
      return
    }
    onPairSelect({
      aId: row.id,
      aName: row.name,
      bId: col.id,
      bName: col.name,
    })
  }

  return (
    <div>
      {/* Category filter (matrix-scoped, doesn't affect the motions table) */}
      <div className="flex flex-wrap items-center gap-1.5 mb-4">
        <span className="text-xs uppercase tracking-wider font-semibold text-slate-400 mr-2">
          Topic
        </span>
        <button
          type="button"
          onClick={() => setSelectedCategory(null)}
          className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
            selectedCategory === null
              ? 'bg-civic-navy text-white'
              : 'bg-white text-slate-600 border border-slate-200 hover:border-slate-300'
          }`}
        >
          All
        </button>
        {categories.map((cat) => (
          <button
            key={cat}
            type="button"
            onClick={() => setSelectedCategory(cat)}
            className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
              selectedCategory === cat
                ? 'bg-civic-navy text-white'
                : 'bg-white text-slate-600 border border-slate-200 hover:border-slate-300'
            }`}
          >
            {formatCategory(cat)}
          </button>
        ))}
      </div>

      {/* Matrix grid — primary control surface */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 overflow-x-auto">
        <table className="w-full text-sm border-separate border-spacing-1">
          <thead>
            <tr>
              <th className="px-2 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-slate-400 sticky left-0 bg-white z-10" />
              {officials.map((o) => (
                <th
                  key={o.id}
                  className="px-1.5 py-2 text-center text-[11px] font-semibold text-slate-500 min-w-[68px]"
                >
                  {lastName(o.name)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {officials.map((row) => (
              <tr key={row.id}>
                <td className="px-2 py-2 text-[11px] font-semibold text-slate-600 whitespace-nowrap sticky left-0 bg-white z-10">
                  {lastName(row.name)}
                </td>
                {officials.map((col) => {
                  if (row.id === col.id) {
                    return (
                      <td
                        key={col.id}
                        className="px-1 py-1 text-center"
                        aria-hidden="true"
                      >
                        <div className="h-12 rounded-md bg-[repeating-linear-gradient(45deg,_#f8fafc_0_4px,_#f1f5f9_4px_8px)]" />
                      </td>
                    )
                  }

                  const alignment = getAlignment(row.id, col.id)
                  const key = pairKey(row.id, col.id)
                  const isSelected = key === selectedKey
                  const isDimmed = selectedKey !== null && !isSelected

                  if (!alignment) {
                    return (
                      <td key={col.id} className="px-1 py-1 text-center">
                        <div className="h-12 rounded-md bg-slate-50 flex items-center justify-center text-[10px] text-slate-300">
                          —
                        </div>
                      </td>
                    )
                  }

                  const pct = Math.round(alignment.agreement_rate * 100)
                  const tone = cellTone(alignment.agreement_rate, alignment.total_shared_votes)
                  const insufficient = alignment.total_shared_votes < 5
                  const labelTopic = selectedCategory ? ` on ${formatCategory(selectedCategory)} votes` : ''
                  const ariaLabel = isSelected
                    ? `${row.name} and ${col.name}: ${pct} percent agreement on ${alignment.total_shared_votes} shared votes${labelTopic}. Selected. Click to clear.`
                    : `${row.name} and ${col.name}: ${pct} percent agreement on ${alignment.total_shared_votes} shared votes${labelTopic}. Click to filter the table below.`

                  return (
                    <td key={col.id} className="px-1 py-1 text-center">
                      <button
                        type="button"
                        onClick={() => handleCellClick(row, col)}
                        aria-pressed={isSelected}
                        aria-label={ariaLabel}
                        title={ariaLabel}
                        className={`group relative h-12 w-full rounded-md ring-1 transition-all duration-150 ${tone} ${
                          isSelected
                            ? 'ring-2 ring-civic-amber shadow-md scale-[1.04] z-10'
                            : isDimmed
                              ? 'opacity-30 hover:opacity-60'
                              : 'hover:ring-2 hover:ring-civic-navy/40 hover:shadow-sm'
                        }`}
                      >
                        <span
                          className={`block tabular-nums text-sm font-bold leading-none ${
                            insufficient ? 'opacity-50 font-medium' : ''
                          }`}
                        >
                          {pct}
                          <span className="text-[9px] font-normal align-top ml-0.5">%</span>
                        </span>
                        {insufficient && (
                          <span className="block mt-0.5 text-[8px] uppercase tracking-wide opacity-60">
                            few votes
                          </span>
                        )}
                      </button>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Legend — compact, right-aligned, secondary */}
      <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-1 mt-3 text-[11px] text-slate-500">
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded bg-emerald-200/70 ring-1 ring-emerald-300" />
          almost always agree
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded bg-amber-100 ring-1 ring-amber-200" />
          mixed
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded bg-rose-300/80 ring-1 ring-rose-400" />
          almost never agree
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded bg-slate-50 ring-1 ring-slate-200" />
          too few votes
        </span>
      </div>
    </div>
  )
}
