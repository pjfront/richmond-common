'use client'

import { useState, useMemo } from 'react'
import type { DonorOverlap } from '@/lib/types'

interface OfficialOption {
  id: string
  name: string
}

interface DonorOverlapSelectorProps {
  overlaps: DonorOverlap[]
}

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount)
}

export default function DonorOverlapSelector({ overlaps }: DonorOverlapSelectorProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  // Extract unique officials from all overlap data
  const officials = useMemo<OfficialOption[]>(() => {
    const map = new Map<string, string>()
    for (const o of overlaps) {
      for (const r of o.recipients) {
        map.set(r.official_id, r.official_name)
      }
    }
    return Array.from(map.entries())
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name))
  }, [overlaps])

  // Filter overlaps to only donors who gave to ALL selected officials
  const filtered = useMemo(() => {
    if (selectedIds.size < 2) return []
    return overlaps
      .filter(o => {
        const recipientIds = new Set(o.recipients.map(r => r.official_id))
        for (const id of selectedIds) {
          if (!recipientIds.has(id)) return false
        }
        return true
      })
      .sort((a, b) => b.total_contributed - a.total_contributed)
  }, [overlaps, selectedIds])

  const toggleOfficial = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const clearSelection = () => setSelectedIds(new Set())

  const selectedNames = officials
    .filter(o => selectedIds.has(o.id))
    .map(o => o.name.split(' ').pop())

  return (
    <div>
      {/* Official selector */}
      <div className="mb-4">
        <p className="text-sm font-medium text-slate-700 mb-2">
          Select 2 or more council members to find shared donors:
        </p>
        <div className="flex flex-wrap gap-2">
          {officials.map(o => {
            const isSelected = selectedIds.has(o.id)
            return (
              <button
                key={o.id}
                type="button"
                onClick={() => toggleOfficial(o.id)}
                className={`px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
                  isSelected
                    ? 'bg-civic-navy text-white shadow-sm'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
                aria-pressed={isSelected}
              >
                {o.name}
              </button>
            )
          })}
          {selectedIds.size > 0 && (
            <button
              type="button"
              onClick={clearSelection}
              className="px-3 py-1.5 rounded-full text-sm font-medium text-slate-400 hover:text-slate-600 transition-colors"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Results */}
      {selectedIds.size === 1 && (
        <p className="text-sm text-slate-500 py-4">
          Select at least one more council member to see shared donors.
        </p>
      )}

      {selectedIds.size >= 2 && (
        <div>
          <div className="flex items-baseline justify-between mb-3">
            <p className="text-sm text-slate-600">
              <span className="font-semibold text-civic-navy">{filtered.length}</span>
              {' '}donor{filtered.length !== 1 ? 's' : ''} contributed to{' '}
              {selectedNames.length === 2
                ? `both ${selectedNames[0]} and ${selectedNames[1]}`
                : `all ${selectedNames.length} selected members`
              }
            </p>
            {filtered.length > 0 && (
              <p className="text-xs text-slate-400">
                {formatCurrency(filtered.reduce((sum, d) => sum + d.total_contributed, 0))} total
              </p>
            )}
          </div>

          {filtered.length === 0 ? (
            <div className="bg-slate-50 rounded-lg border border-slate-200 p-6 text-center">
              <p className="text-slate-500 text-sm">
                No shared donors found between these officials.
              </p>
            </div>
          ) : (
            <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
              <table className="w-full text-sm">
                <caption className="sr-only">
                  Donors who contributed to {selectedNames.join(', ')}
                </caption>
                <thead className="bg-slate-50 border-b border-slate-200">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                      Donor
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-semibold text-slate-600 uppercase tracking-wider">
                      Total
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider hidden sm:table-cell">
                      Distribution
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filtered.map(donor => {
                    // Only show recipients that are in the selected set
                    const relevantRecipients = donor.recipients
                      .filter(r => selectedIds.has(r.official_id))
                      .sort((a, b) => b.amount - a.amount)

                    return (
                      <tr key={donor.donor_id} className="hover:bg-slate-50 transition-colors">
                        <td className="px-4 py-3">
                          <span className="font-medium text-slate-700">{donor.donor_name}</span>
                          {donor.donor_employer && (
                            <p className="text-xs text-slate-400 mt-0.5">{donor.donor_employer}</p>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums font-medium text-slate-700">
                          {formatCurrency(donor.total_contributed)}
                        </td>
                        <td className="px-4 py-3 hidden sm:table-cell">
                          <div className="flex flex-wrap gap-x-4 gap-y-1">
                            {relevantRecipients.map(r => (
                              <span key={r.official_id} className="text-xs text-slate-600">
                                <span className="font-medium">{r.official_name.split(' ').pop()}</span>
                                {' '}
                                <span className="text-slate-400 tabular-nums">
                                  {formatCurrency(r.amount)} ({r.contribution_count})
                                </span>
                              </span>
                            ))}
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          <p className="text-[11px] text-slate-400 mt-3">
            Contribution data from NetFile (local) and CAL-ACCESS (state) public filings.
            Contributing to multiple officials is common and does not imply coordination.
          </p>
        </div>
      )}
    </div>
  )
}
