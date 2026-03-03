'use client'

import { useMemo, useState } from 'react'
import type { PairwiseAlignment } from '@/lib/types'
import { formatCategory } from '@/components/CategoryBadge'

interface AlignmentMatrixProps {
  alignments: PairwiseAlignment[]
  officials: Array<{ id: string; name: string }>
  categories: string[]
}

export default function AlignmentMatrix({ alignments, officials, categories }: AlignmentMatrixProps) {
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)

  // Build lookup: "idA|idB" -> alignment for current category filter
  const pairLookup = useMemo(() => {
    const map = new Map<string, PairwiseAlignment>()
    for (const a of alignments) {
      if (a.category === selectedCategory) {
        const key = `${a.official_a_id}|${a.official_b_id}`
        map.set(key, a)
      }
    }
    return map
  }, [alignments, selectedCategory])

  const getAlignment = (idA: string, idB: string): PairwiseAlignment | undefined => {
    const [first, second] = idA < idB ? [idA, idB] : [idB, idA]
    return pairLookup.get(`${first}|${second}`)
  }

  const getCellColor = (rate: number, votes: number): string => {
    if (votes < 5) return 'bg-slate-100 text-slate-400'
    if (rate >= 0.85) return 'bg-emerald-100 text-emerald-800'
    if (rate >= 0.70) return 'bg-emerald-50 text-emerald-700'
    if (rate >= 0.50) return 'bg-amber-50 text-amber-800'
    return 'bg-red-50 text-red-800'
  }

  // Get last name for compact display
  const lastName = (name: string) => {
    const parts = name.split(' ')
    return parts[parts.length - 1]
  }

  return (
    <div>
      {/* Category filter */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <span className="text-sm font-medium text-slate-600">Filter:</span>
        <button
          onClick={() => setSelectedCategory(null)}
          className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
            selectedCategory === null
              ? 'bg-civic-navy text-white'
              : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
          }`}
        >
          All Topics
        </button>
        {categories.map((cat) => (
          <button
            key={cat}
            onClick={() => setSelectedCategory(cat)}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              selectedCategory === cat
                ? 'bg-civic-navy text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            {formatCategory(cat)}
          </button>
        ))}
      </div>

      {/* Matrix grid */}
      <div className="bg-white rounded-lg border border-slate-200 overflow-x-auto">
        <table className="text-sm">
          <thead>
            <tr>
              <th className="px-3 py-3 text-left text-xs font-semibold text-slate-600 bg-slate-50 sticky left-0 z-10 border-r border-slate-200" />
              {officials.map((o) => (
                <th
                  key={o.id}
                  className="px-3 py-3 text-center text-xs font-semibold text-slate-600 bg-slate-50 min-w-[80px]"
                >
                  {lastName(o.name)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {officials.map((row) => (
              <tr key={row.id}>
                <td className="px-3 py-2 text-xs font-medium text-slate-700 whitespace-nowrap bg-slate-50 sticky left-0 z-10 border-r border-slate-200">
                  {lastName(row.name)}
                </td>
                {officials.map((col) => {
                  if (row.id === col.id) {
                    return (
                      <td key={col.id} className="px-3 py-2 text-center bg-slate-50">
                        <span className="text-slate-300 text-xs">&mdash;</span>
                      </td>
                    )
                  }

                  const alignment = getAlignment(row.id, col.id)
                  if (!alignment) {
                    return (
                      <td key={col.id} className="px-3 py-2 text-center bg-slate-50">
                        <span className="text-slate-300 text-xs">n/a</span>
                      </td>
                    )
                  }

                  const pct = Math.round(alignment.agreement_rate * 100)
                  const insufficient = alignment.total_shared_votes < 5

                  return (
                    <td
                      key={col.id}
                      className={`px-3 py-2 text-center ${getCellColor(alignment.agreement_rate, alignment.total_shared_votes)}`}
                      title={`${row.name} & ${col.name}: ${pct}% agreement on ${alignment.total_shared_votes} shared votes${selectedCategory ? ` (${formatCategory(selectedCategory)})` : ''}`}
                    >
                      <span className={`tabular-nums text-xs font-semibold ${insufficient ? 'text-slate-400 font-normal' : ''}`}>
                        {pct}%
                      </span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-3 mt-3 text-xs text-slate-500">
        <span className="font-medium">Legend:</span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded bg-emerald-100 border border-emerald-200" /> 85%+ aligned
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded bg-emerald-50 border border-emerald-100" /> 70-84%
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded bg-amber-50 border border-amber-100" /> 50-69%
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded bg-red-50 border border-red-100" /> &lt;50% divergent
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded bg-slate-100 border border-slate-200" /> &lt;5 shared votes
        </span>
      </div>
    </div>
  )
}
