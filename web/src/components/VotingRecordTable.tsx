'use client'

import { useState, useMemo } from 'react'
import Link from 'next/link'
import VoteBadge from './VoteBadge'

interface VoteRecord {
  id: string
  vote_choice: string
  meeting_id: string
  meeting_date: string
  meeting_type: string
  item_number: string
  item_title: string
  category: string | null
  motion_result: string
  is_consent_calendar: boolean
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function VotingRecordTable({ votes }: { votes: VoteRecord[] }) {
  const [categoryFilter, setCategoryFilter] = useState<string>('all')
  const [choiceFilter, setChoiceFilter] = useState<string>('all')
  const [hideConsent, setHideConsent] = useState(false)
  const [showAll, setShowAll] = useState(false)

  const categories = useMemo(() => {
    const cats = new Set<string>()
    for (const v of votes) {
      if (v.category) cats.add(v.category)
    }
    return Array.from(cats).sort()
  }, [votes])

  const filtered = useMemo(() => {
    return votes.filter((v) => {
      if (categoryFilter !== 'all' && v.category !== categoryFilter) return false
      if (choiceFilter !== 'all' && v.vote_choice.toLowerCase() !== choiceFilter) return false
      if (hideConsent && v.is_consent_calendar) return false
      return true
    })
  }, [votes, categoryFilter, choiceFilter, hideConsent])

  const visible = showAll ? filtered : filtered.slice(0, 25)

  if (votes.length === 0) {
    return <p className="text-sm text-slate-500 italic">No voting record available.</p>
  }

  function formatCategory(cat: string): string {
    return cat.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  }

  return (
    <div>
      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4">
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="text-sm border border-slate-200 rounded px-2 py-1 text-slate-700"
        >
          <option value="all">All Categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {formatCategory(c)}
            </option>
          ))}
        </select>
        <select
          value={choiceFilter}
          onChange={(e) => setChoiceFilter(e.target.value)}
          className="text-sm border border-slate-200 rounded px-2 py-1 text-slate-700"
        >
          <option value="all">All Votes</option>
          <option value="aye">Aye</option>
          <option value="nay">Nay</option>
          <option value="abstain">Abstain</option>
          <option value="absent">Absent</option>
        </select>
        <label className="flex items-center gap-1.5 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={hideConsent}
            onChange={(e) => setHideConsent(e.target.checked)}
            className="rounded"
          />
          Hide consent calendar
        </label>
        <span className="text-xs text-slate-400 self-center">
          {filtered.length} of {votes.length} votes
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left">
              <th className="py-2 pr-3 font-medium text-slate-600">Date</th>
              <th className="py-2 pr-3 font-medium text-slate-600">Item</th>
              <th className="py-2 pr-3 font-medium text-slate-600 hidden md:table-cell">Category</th>
              <th className="py-2 pr-3 font-medium text-slate-600">Vote</th>
              <th className="py-2 font-medium text-slate-600 hidden sm:table-cell">Result</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((v) => (
              <tr key={v.id} className="border-b border-slate-100">
                <td className="py-2 pr-3 text-slate-500 whitespace-nowrap">
                  <Link
                    href={`/meetings/${v.meeting_id}`}
                    className="hover:text-civic-navy-light"
                  >
                    {formatDate(v.meeting_date)}
                  </Link>
                </td>
                <td className="py-2 pr-3 text-slate-900">
                  <span className="text-xs font-mono text-slate-400 mr-1">{v.item_number}</span>
                  <span className="line-clamp-1">{v.item_title}</span>
                </td>
                <td className="py-2 pr-3 text-xs text-slate-500 hidden md:table-cell">
                  {v.category ? formatCategory(v.category) : '\u2014'}
                </td>
                <td className="py-2 pr-3">
                  <VoteBadge choice={v.vote_choice} />
                </td>
                <td className="py-2 text-xs text-slate-500 capitalize hidden sm:table-cell">
                  {v.motion_result}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!showAll && filtered.length > 25 && (
        <button
          onClick={() => setShowAll(true)}
          className="mt-2 text-sm text-civic-navy-light hover:text-civic-navy"
        >
          Show all {filtered.length} votes
        </button>
      )}
    </div>
  )
}
