'use client'

import { useState } from 'react'
import type { DonorAggregate } from '@/lib/types'

type SortKey = 'total_amount' | 'contribution_count' | 'donor_name'

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount)
}

export default function DonorTable({ donors }: { donors: DonorAggregate[] }) {
  const [sortKey, setSortKey] = useState<SortKey>('total_amount')
  const [sortAsc, setSortAsc] = useState(false)
  const [showAll, setShowAll] = useState(false)

  if (donors.length === 0) {
    return (
      <p className="text-sm text-slate-500 italic">No contribution data available.</p>
    )
  }

  const sorted = [...donors].sort((a, b) => {
    let cmp = 0
    if (sortKey === 'donor_name') {
      cmp = a.donor_name.localeCompare(b.donor_name)
    } else {
      cmp = a[sortKey] - b[sortKey]
    }
    return sortAsc ? cmp : -cmp
  })

  const visible = showAll ? sorted : sorted.slice(0, 10)

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortAsc(!sortAsc)
    } else {
      setSortKey(key)
      setSortAsc(false)
    }
  }

  const arrow = (key: SortKey) =>
    sortKey === key ? (sortAsc ? ' \u2191' : ' \u2193') : ''

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left">
              <th
                className="py-2 pr-4 font-medium text-slate-600 cursor-pointer hover:text-civic-navy"
                onClick={() => handleSort('donor_name')}
              >
                Donor{arrow('donor_name')}
              </th>
              <th className="py-2 pr-4 font-medium text-slate-600 hidden sm:table-cell">
                Employer
              </th>
              <th
                className="py-2 pr-4 font-medium text-slate-600 text-right cursor-pointer hover:text-civic-navy"
                onClick={() => handleSort('total_amount')}
              >
                Total{arrow('total_amount')}
              </th>
              <th
                className="py-2 pr-4 font-medium text-slate-600 text-right cursor-pointer hover:text-civic-navy"
                onClick={() => handleSort('contribution_count')}
              >
                #{arrow('contribution_count')}
              </th>
              <th className="py-2 font-medium text-slate-600 hidden md:table-cell">Source</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((d, i) => (
              <tr key={`${d.donor_name}-${i}`} className="border-b border-slate-100">
                <td className="py-2 pr-4 text-slate-900">{d.donor_name}</td>
                <td className="py-2 pr-4 text-slate-500 hidden sm:table-cell">
                  {d.donor_employer ?? '\u2014'}
                </td>
                <td className="py-2 pr-4 text-right font-medium text-slate-900">
                  {formatCurrency(d.total_amount)}
                </td>
                <td className="py-2 pr-4 text-right text-slate-500">{d.contribution_count}</td>
                <td className="py-2 text-xs text-slate-400 hidden md:table-cell">{d.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!showAll && sorted.length > 10 && (
        <button
          onClick={() => setShowAll(true)}
          className="mt-2 text-sm text-civic-navy-light hover:text-civic-navy"
        >
          Show all {sorted.length} donors
        </button>
      )}
    </div>
  )
}
