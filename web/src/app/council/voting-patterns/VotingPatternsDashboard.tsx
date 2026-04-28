'use client'

import { useMemo, useState } from 'react'
import AlignmentMatrix, { type SelectedPair } from '@/components/AlignmentMatrix'
import BlocSummary from '@/components/BlocSummary'
import DivergentMotionsTable from '@/components/DivergentMotionsTable'
import LastUpdated from '@/components/LastUpdated'
import MemberPicker from '@/components/MemberPicker'
import { formatCategory } from '@/components/CategoryBadge'
import type {
  CategoryDivergence,
  DivergentMotion,
  PairwiseAlignment,
  VotingBloc,
} from '@/lib/types'

interface VotingPatternsDashboardProps {
  alignments: PairwiseAlignment[]
  blocs: VotingBloc[]
  divergences: CategoryDivergence[]  // unused after Phase A2 redesign; kept in props for backward query compat
  coalitionOfficials: Array<{ id: string; name: string }>
  motions: DivergentMotion[]
  motionOfficials: Array<{ id: string; name: string }>
}

function lastName(full: string): string {
  return full.trim().split(/\s+/).pop() ?? full
}

export default function VotingPatternsDashboard({
  alignments,
  blocs,
  coalitionOfficials,
  motions,
  motionOfficials,
}: VotingPatternsDashboardProps) {
  const [includeProcedural, setIncludeProcedural] = useState(false)
  const [selectedPair, setSelectedPair] = useState<SelectedPair | null>(null)
  const [selectedOfficials, setSelectedOfficials] = useState<Set<string>>(
    () => new Set(motionOfficials.map((o) => o.id)),
  )
  const [searchQuery, setSearchQuery] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<string>('all')

  // Categories that actually appear in the divergent motions (sorted)
  const motionCategories = useMemo(() => {
    const set = new Set<string>()
    for (const m of motions) {
      if (m.category) set.add(m.category)
    }
    return Array.from(set).sort()
  }, [motions])

  // Categories for the alignment matrix's own filter
  const matrixCategories = useMemo(
    () =>
      Array.from(
        new Set(alignments.filter((a) => a.category !== null).map((a) => a.category as string)),
      ).sort(),
    [alignments],
  )

  const filteredMotions = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    return motions.filter((m) => {
      if (!includeProcedural && m.is_procedural) return false
      if (categoryFilter !== 'all' && m.category !== categoryFilter) return false

      if (selectedPair) {
        // Pair-disagree filter: both members voted aye/nay AND they voted differently
        const a = m.votes[selectedPair.aId]
        const b = m.votes[selectedPair.bId]
        const bothVoted = (a === 'aye' || a === 'nay') && (b === 'aye' || b === 'nay')
        if (!bothVoted || a === b) return false
      } else if (selectedOfficials.size < motionOfficials.length) {
        // MemberPicker subset filter: motions where the selected members split among themselves
        const choices = new Set<string>()
        for (const id of selectedOfficials) {
          const choice = m.votes[id]
          if (choice === 'aye' || choice === 'nay') choices.add(choice)
        }
        if (choices.size < 2) return false
      }

      if (q) {
        const haystack = `${m.motion_text ?? ''} ${m.agenda_item_title ?? ''} ${m.topic_label ?? ''}`.toLowerCase()
        if (!haystack.includes(q)) return false
      }
      return true
    })
  }, [motions, motionOfficials, includeProcedural, selectedPair, selectedOfficials, categoryFilter, searchQuery])

  const proceduralHidden = useMemo(
    () => motions.filter((m) => m.is_procedural).length,
    [motions],
  )

  // Table column logic. Pair selection (matrix click) is a row filter only —
  // it picks WHICH motions to show. Columns stay full so the user can see how
  // the rest of the council voted on those same motions for context.
  const tableSelectedOfficials = useMemo(() => {
    if (selectedPair) return new Set(motionOfficials.map((o) => o.id))
    return selectedOfficials
  }, [selectedPair, selectedOfficials, motionOfficials])

  const filtersAreActive =
    selectedPair !== null ||
    searchQuery.trim() !== '' ||
    categoryFilter !== 'all' ||
    selectedOfficials.size < motionOfficials.length

  function clearAllFilters() {
    setSelectedPair(null)
    setSearchQuery('')
    setCategoryFilter('all')
    setSelectedOfficials(new Set(motionOfficials.map((o) => o.id)))
  }

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      {/* ── Header ─────────────────────────────────────────────── */}
      <header className="mb-8">
        <h1 className="text-3xl sm:text-4xl font-bold text-civic-navy tracking-tight mb-2">
          How the Council Votes
        </h1>
        <p className="text-slate-600 max-w-2xl leading-relaxed">
          See where your council members vote together and where they split.
          Tap any square to see exactly what those two members disagreed on.
        </p>
      </header>

      {/* ── Hero: Alignment Matrix as control surface ──────────── */}
      <section className="mb-6">
        <AlignmentMatrix
          alignments={alignments}
          officials={coalitionOfficials}
          categories={matrixCategories}
          selectedPair={selectedPair}
          onPairSelect={setSelectedPair}
        />
      </section>

      {/* ── Selection context strip ────────────────────────────── */}
      <div
        className={`mb-8 rounded-lg border px-4 py-3 transition-colors ${
          selectedPair
            ? 'border-civic-amber/50 bg-civic-amber/5'
            : 'border-slate-200 bg-slate-50'
        }`}
        aria-live="polite"
      >
        {selectedPair ? (
          <div className="flex items-center justify-between flex-wrap gap-3">
            <p className="text-sm text-slate-700">
              <span className="text-slate-500">Showing</span>{' '}
              <span className="font-semibold text-civic-navy">
                {filteredMotions.length} {filteredMotions.length === 1 ? 'vote' : 'votes'}
              </span>{' '}
              <span className="text-slate-500">where</span>{' '}
              <span className="font-semibold text-slate-800">{lastName(selectedPair.aName)}</span>{' '}
              <span className="text-slate-500">and</span>{' '}
              <span className="font-semibold text-slate-800">{lastName(selectedPair.bName)}</span>{' '}
              <span className="text-slate-500">voted differently</span>
            </p>
            <button
              type="button"
              onClick={() => setSelectedPair(null)}
              className="text-xs font-medium text-civic-navy hover:text-civic-navy-light underline-offset-2 hover:underline"
            >
              Show all members ×
            </button>
          </div>
        ) : (
          <p className="text-sm text-slate-600">
            <span className="font-medium">Tip:</span> Tap any square in the grid above to see what
            those two members disagreed on.
          </p>
        )}
      </div>

      {/* ── Filter bar ─────────────────────────────────────────── */}
      <div className="mb-4">
        <div className="flex flex-wrap items-center gap-3 px-4 py-3 rounded-lg border border-slate-200 bg-white shadow-sm">
          {/* Search */}
          <div className="relative flex-1 min-w-[220px]">
            <svg
              aria-hidden="true"
              className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 21l-4.35-4.35M11 19a8 8 0 1 1 0-16 8 8 0 0 1 0 16z"
              />
            </svg>
            <input
              type="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search what was voted on…"
              aria-label="Search votes by what was voted on"
              className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-civic-navy/30 focus:border-civic-navy/40"
            />
          </div>

          {/* Category */}
          <div className="flex items-center gap-2">
            <label htmlFor="cat-filter" className="text-xs uppercase tracking-wider font-semibold text-slate-400">
              Topic
            </label>
            <select
              id="cat-filter"
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="text-sm border border-slate-200 rounded-md px-2 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-civic-navy/30 focus:border-civic-navy/40"
            >
              <option value="all">All topics</option>
              {motionCategories.map((c) => (
                <option key={c} value={c}>
                  {formatCategory(c)}
                </option>
              ))}
            </select>
          </div>

          {/* Procedural */}
          <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={includeProcedural}
              onChange={(e) => setIncludeProcedural(e.target.checked)}
              className="w-4 h-4 rounded border-slate-300 text-civic-navy focus:ring-civic-navy"
            />
            <span>
              Include procedural votes
              {proceduralHidden > 0 && !includeProcedural && (
                <span className="text-slate-400 text-xs ml-1">({proceduralHidden} hidden)</span>
              )}
            </span>
          </label>

          {/* Clear */}
          {filtersAreActive && (
            <button
              type="button"
              onClick={clearAllFilters}
              className="ml-auto text-xs font-medium text-slate-500 hover:text-civic-navy underline-offset-2 hover:underline"
            >
              Clear filters
            </button>
          )}
        </div>

        {/* Member picker — only when no pair is selected */}
        {!selectedPair && (
          <div className="mt-3 px-4">
            <MemberPicker
              officials={motionOfficials}
              selected={selectedOfficials}
              onChange={setSelectedOfficials}
            />
          </div>
        )}
      </div>

      {/* ── Result count + table ───────────────────────────────── */}
      <p className="text-xs text-slate-500 mb-3 px-1">
        Showing {filteredMotions.length} of {motions.length} split{' '}
        {motions.length === 1 ? 'vote' : 'votes'}
      </p>

      <section className="mb-12">
        <DivergentMotionsTable
          motions={filteredMotions}
          officials={motionOfficials}
          selectedOfficials={tableSelectedOfficials}
        />
      </section>

      {/* ── Voting groups (secondary, demoted) ─────────────────── */}
      {blocs.length > 0 && (
        <section className="mb-12">
          <h2 className="text-lg font-semibold text-slate-800 mb-1">
            Voting groups
          </h2>
          <p className="text-sm text-slate-500 mb-4 max-w-2xl">
            Members who tend to vote the same way on split votes — three or more
            who agree most of the time.
          </p>
          <BlocSummary blocs={blocs} />
        </section>
      )}

      {/* ── Methodology (calmly at the end) ────────────────────── */}
      <section className="bg-slate-50 rounded-lg border border-slate-200 p-5 text-sm text-slate-600">
        <h3 className="font-semibold text-slate-700 mb-3">How this is built</h3>
        <p className="mb-2">
          <strong>Split votes only.</strong> This page sets aside votes where
          everyone agreed. Only motions with at least one yes and one no vote
          are included, so you can see where members actually take different
          positions.
        </p>
        <p className="mb-2">
          <strong>The percentage in each square</strong> is the share of split
          votes where those two members voted the same direction. Members who
          were absent or abstained on a given motion are not counted in that
          motion. Squares with too few shared votes (under five) are dimmed.
        </p>
        <p className="mb-2">
          <strong>Procedural votes</strong> are motions about how the meeting
          runs — extending the meeting, referring items to committee, limiting
          public comment — not about the underlying issue. Hidden by default;
          toggle them on to spot patterns like running out the clock on
          contested items.
        </p>
        <p>
          Vote records come from official meeting minutes. Percentages reflect
          recorded votes only — they don&apos;t imply coordination, shared
          ideology, or political affiliation.
        </p>
      </section>

      <LastUpdated />
    </div>
  )
}
