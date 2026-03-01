'use client'

import { useMemo, useState } from 'react'
import OperatorGate from './OperatorGate'
import type { EconomicInterest } from '@/lib/types'

/** Human-readable labels for Form 700 schedules */
const SCHEDULE_LABELS: Record<string, string> = {
  'A-1': 'Investments',
  'A-2': 'Investments (Additional)',
  'B': 'Real Property',
  'C': 'Income',
  'D': 'Gifts',
  'E': 'Travel / Payments',
}

/** Human-readable labels for interest types */
const TYPE_LABELS: Record<string, string> = {
  real_property: 'Real Property',
  investment: 'Investment',
  income: 'Income',
  gift: 'Gift',
  business_position: 'Business Position',
}

function formatPeriod(periodStart: string | null, periodEnd: string | null): string {
  if (!periodStart && !periodEnd) return ''
  if (periodEnd) {
    const end = new Date(periodEnd + 'T00:00:00')
    return `Period ending ${end.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}`
  }
  return `Filed ${periodStart}`
}

interface EconomicInterestsTableProps {
  interests: EconomicInterest[]
  officialName: string
}

export default function EconomicInterestsTable({
  interests,
  officialName,
}: EconomicInterestsTableProps) {
  const [expandedYear, setExpandedYear] = useState<number | null>(null)

  // Group by filing year, then by schedule within each year
  const groupedByYear = useMemo(() => {
    const yearMap = new Map<number, EconomicInterest[]>()
    for (const interest of interests) {
      const arr = yearMap.get(interest.filing_year) ?? []
      arr.push(interest)
      yearMap.set(interest.filing_year, arr)
    }
    // Sort years descending
    return Array.from(yearMap.entries())
      .sort(([a], [b]) => b - a)
  }, [interests])

  if (interests.length === 0) return null

  // Auto-expand the most recent year
  const activeYear = expandedYear ?? groupedByYear[0]?.[0] ?? null

  return (
    <OperatorGate>
      <section className="mb-8">
        <div className="flex items-center gap-2 mb-3">
          <h2 className="text-xl font-semibold text-slate-800">
            Financial Disclosures
          </h2>
          <span className="text-xs bg-amber-100 text-amber-800 px-2 py-0.5 rounded font-medium">
            Operator Only
          </span>
        </div>

        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <p className="text-xs text-slate-500 mb-4">
            Reported interests from {officialName}&apos;s Form 700 (Statement of Economic Interests) filings.
            Data extracted from FPPC and NetFile SEI public records.
          </p>

          {/* Year tabs */}
          <div className="flex gap-2 mb-4 flex-wrap">
            {groupedByYear.map(([year]) => (
              <button
                key={year}
                onClick={() => setExpandedYear(year)}
                className={`px-3 py-1 text-sm rounded transition-colors ${
                  year === activeYear
                    ? 'bg-civic-navy text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {year}
              </button>
            ))}
          </div>

          {/* Interests for the active year, grouped by schedule */}
          {activeYear !== null && (
            <YearInterests
              interests={groupedByYear.find(([y]) => y === activeYear)?.[1] ?? []}
            />
          )}
        </div>
      </section>
    </OperatorGate>
  )
}

function YearInterests({ interests }: { interests: EconomicInterest[] }) {
  // Group by schedule
  const scheduleGroups = useMemo(() => {
    const map = new Map<string, EconomicInterest[]>()
    for (const interest of interests) {
      const arr = map.get(interest.schedule) ?? []
      arr.push(interest)
      map.set(interest.schedule, arr)
    }
    // Sort by schedule order: A-1, A-2, B, C, D, E
    const order = ['A-1', 'A-2', 'B', 'C', 'D', 'E']
    return Array.from(map.entries())
      .sort(([a], [b]) => order.indexOf(a) - order.indexOf(b))
  }, [interests])

  // Filing period from any interest (they share the same filing)
  const sampleInterest = interests[0]
  const periodText = sampleInterest
    ? formatPeriod(sampleInterest.period_start, sampleInterest.period_end)
    : ''

  return (
    <div className="space-y-4">
      {periodText && (
        <p className="text-xs text-slate-400">{periodText}</p>
      )}
      {scheduleGroups.map(([schedule, items]) => (
        <div key={schedule}>
          <h3 className="text-sm font-medium text-slate-700 mb-2">
            Schedule {schedule}: {SCHEDULE_LABELS[schedule] ?? schedule}
            <span className="text-slate-400 font-normal ml-2">({items.length})</span>
          </h3>
          <div className="space-y-1.5">
            {items.map((item) => (
              <InterestRow key={item.id} interest={item} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function InterestRow({ interest }: { interest: EconomicInterest }) {
  return (
    <div className="flex items-start gap-3 py-1.5 px-2 rounded hover:bg-slate-50 text-sm">
      <span className="shrink-0 text-xs text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded mt-0.5">
        {TYPE_LABELS[interest.interest_type] ?? interest.interest_type}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-slate-800">{interest.description}</p>
        <div className="flex gap-3 text-xs text-slate-400 mt-0.5">
          {interest.value_range && <span>{interest.value_range}</span>}
          {interest.location && <span>{interest.location}</span>}
        </div>
      </div>
      {(interest.filing_source_url || interest.source_url) && (
        <a
          href={interest.filing_source_url ?? interest.source_url ?? '#'}
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0 text-xs text-civic-navy-light hover:text-civic-navy underline mt-0.5"
        >
          Source
        </a>
      )}
    </div>
  )
}
