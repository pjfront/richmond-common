'use client'

import { useState, useCallback } from 'react'

interface DateFilterBarProps {
  onChange: (range: { start: string; end: string }) => void
  defaultStart: string
  defaultEnd: string
}

function getYearRange(year: number) {
  return { start: `${year}-01-01`, end: `${year}-12-31` }
}

export default function DateFilterBar({ onChange, defaultStart, defaultEnd }: DateFilterBarProps) {
  const [start, setStart] = useState(defaultStart)
  const [end, setEnd] = useState(defaultEnd)
  const [activeShortcut, setActiveShortcut] = useState<string>('this_year')

  const currentYear = new Date().getFullYear()

  const applyRange = useCallback(
    (s: string, e: string, shortcut: string) => {
      setStart(s)
      setEnd(e)
      setActiveShortcut(shortcut)
      onChange({ start: s, end: e })
    },
    [onChange]
  )

  const shortcuts = [
    { label: 'This year', key: 'this_year', range: getYearRange(currentYear) },
    { label: 'Last year', key: 'last_year', range: getYearRange(currentYear - 1) },
    { label: 'All time', key: 'all_time', range: { start: '2000-01-01', end: `${currentYear}-12-31` } },
  ]

  return (
    <div className="flex flex-wrap items-center gap-3 py-4">
      <div className="flex items-center gap-2 text-sm">
        <label htmlFor="date-start" className="text-slate-500">From</label>
        <input
          id="date-start"
          type="date"
          value={start}
          onChange={(e) => {
            setStart(e.target.value)
            setActiveShortcut('')
            onChange({ start: e.target.value, end })
          }}
          className="border border-slate-300 rounded px-2 py-1 text-sm text-slate-700"
        />
        <label htmlFor="date-end" className="text-slate-500">to</label>
        <input
          id="date-end"
          type="date"
          value={end}
          onChange={(e) => {
            setEnd(e.target.value)
            setActiveShortcut('')
            onChange({ start, end: e.target.value })
          }}
          className="border border-slate-300 rounded px-2 py-1 text-sm text-slate-700"
        />
      </div>
      <div className="flex gap-1.5">
        {shortcuts.map((sc) => (
          <button
            key={sc.key}
            onClick={() => applyRange(sc.range.start, sc.range.end, sc.key)}
            className={`text-xs px-2.5 py-1 rounded-full transition-colors ${
              activeShortcut === sc.key
                ? 'bg-civic-navy text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            {sc.label}
          </button>
        ))}
      </div>
    </div>
  )
}
