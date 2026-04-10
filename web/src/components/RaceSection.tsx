'use client'

import { useState, useEffect, useRef } from 'react'
import * as Collapsible from '@radix-ui/react-collapsible'
import type { CandidateFundraisingDetail } from '@/lib/types'
import { buildRaceNarrative } from '@/lib/electionNarrative'
import CandidateCard from './CandidateCard'

interface RaceSectionProps {
  office: string
  candidates: CandidateFundraisingDetail[]
  /** Mayor gets hero treatment */
  isHeroRace?: boolean
  /** URL hash anchor, e.g. "mayor" or "district-3" */
  id: string
  /** Election slug for candidate profile links, e.g. "2026-primary" */
  electionSlug?: string
}

export default function RaceSection({
  office,
  candidates,
  isHeroRace = false,
  id,
  electionSlug,
}: RaceSectionProps) {
  const isUnopposed = candidates.length === 1
  const isContested = candidates.length > 1
  const showRoster = candidates.length >= 2

  if (isUnopposed) {
    return <UnopposedSection office={office} candidate={candidates[0]} id={id} />
  }

  return (
    <ContestedSection
      office={office}
      candidates={candidates}
      isHeroRace={isHeroRace}
      showRoster={showRoster}
      id={id}
      defaultExpanded={isHeroRace}
      electionSlug={electionSlug}
    />
  )
}

// ─── Path 3: Unopposed ──────────────────────────────────────────────

function UnopposedSection({
  office,
  candidate,
  id,
}: {
  office: string
  candidate: CandidateFundraisingDetail
  id: string
}) {
  const narrative = buildRaceNarrative(office, [candidate])

  return (
    <section id={id} aria-label={`${office} — Unopposed`} className="mb-4 scroll-mt-20">
      <div className="flex items-center gap-2">
        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
          {office}
        </h2>
        <span className="text-xs text-slate-400">· 1 candidate · unopposed</span>
      </div>
      {narrative && (
        <p className="text-sm text-slate-500 mt-1.5 leading-relaxed">{narrative}</p>
      )}
    </section>
  )
}

// ─── Paths 1 & 2: Contested ─────────────────────────────────────────

function ContestedSection({
  office,
  candidates,
  isHeroRace,
  showRoster,
  id,
  defaultExpanded,
  electionSlug,
}: {
  office: string
  candidates: CandidateFundraisingDetail[]
  isHeroRace: boolean
  showRoster: boolean
  id: string
  defaultExpanded: boolean
  electionSlug?: string
}) {
  const sectionRef = useRef<HTMLElement>(null)
  const [open, setOpen] = useState(defaultExpanded)

  // Hash-based auto-expand
  useEffect(() => {
    function checkHash() {
      const hash = window.location.hash.replace('#', '')
      if (hash === id && !open) {
        setOpen(true)
        // Delay scroll to allow animation
        setTimeout(() => {
          sectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }, 100)
      }
    }
    checkHash()
    window.addEventListener('hashchange', checkHash)
    return () => window.removeEventListener('hashchange', checkHash)
  }, [id]) // eslint-disable-line react-hooks/exhaustive-deps

  const narrative = buildRaceNarrative(office, candidates)

  const labelClass = isHeroRace
    ? 'text-sm font-semibold text-civic-navy uppercase tracking-wide'
    : 'text-xs font-semibold text-slate-500 uppercase tracking-wide'

  const cardClass = [
    'bg-white border rounded-lg p-5',
    isHeroRace
      ? 'border-civic-navy/20 border-l-3 border-l-civic-navy bg-gradient-to-r from-civic-navy/[0.03] to-transparent'
      : 'border-slate-200 border-l-3 border-l-civic-navy/60',
    'mb-8 scroll-mt-20',
  ].join(' ')

  return (
    <Collapsible.Root open={open} onOpenChange={setOpen} asChild>
      <section ref={sectionRef} id={id} className={cardClass}>
        {/* Header row: label + chevron */}
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h2 className={labelClass}>{office}</h2>
              <span className="text-xs text-slate-400">
                · {candidates.length} candidate{candidates.length !== 1 ? 's' : ''}
              </span>
            </div>

            {/* Narrative lede — always visible */}
            {narrative && (
              <p className="text-sm text-slate-600 mt-2 leading-relaxed">
                {narrative}
              </p>
            )}

            {/* Roster strip for 3+ candidates — always visible */}
            {showRoster && (
              <CandidateRosterStrip candidates={candidates} />
            )}
          </div>

          {/* Chevron toggle */}
          <Collapsible.Trigger asChild>
            <button
              className="p-3.5 -m-1.5 rounded-md text-slate-400 hover:text-civic-navy hover:bg-slate-50 transition-colors focus-visible:outline-2 focus-visible:outline-civic-navy shrink-0"
              aria-label={open ? `Collapse ${office} details` : `Expand ${office} details`}
            >
              <ChevronIcon open={open} />
            </button>
          </Collapsible.Trigger>
        </div>

        {/* Expanded: full candidate cards */}
        <Collapsible.Content className="collapsible-content overflow-hidden">
          <div className="mt-4 pt-4 border-t border-slate-100 space-y-3">
            {candidates.map((candidate) => (
              <CandidateCard key={candidate.candidate_name} candidate={candidate} electionSlug={electionSlug} />
            ))}
          </div>
        </Collapsible.Content>
      </section>
    </Collapsible.Root>
  )
}

// ─── Roster strip (3+ candidates) ───────────────────────────────────

function CandidateRosterStrip({
  candidates,
}: {
  candidates: CandidateFundraisingDetail[]
}) {
  const sorted = [...candidates].sort(
    (a, b) => b.total_raised - a.total_raised,
  )

  return (
    <ul className="mt-3 space-y-1" aria-label="Candidate overview">
      {sorted.map((c) => (
        <li
          key={c.candidate_name}
          className="flex items-center justify-between text-sm gap-3"
        >
          <span className="min-w-0 truncate">
            <span className="font-medium text-civic-navy">
              {c.candidate_name}
            </span>
            {c.is_incumbent && (
              <span className="ml-1.5 inline-block px-1.5 py-0.5 text-[10px] font-medium bg-civic-navy/10 text-civic-navy rounded">
                incumbent
              </span>
            )}
          </span>
          <span className="text-slate-400 tabular-nums whitespace-nowrap shrink-0 text-xs">
            {c.total_raised > 0
              ? `$${c.total_raised.toLocaleString('en-US', { maximumFractionDigits: 0 })} · ${c.donor_count} donor${c.donor_count !== 1 ? 's' : ''}`
              : 'No filings linked'}
          </span>
        </li>
      ))}
    </ul>
  )
}

// ─── Chevron icon ───────────────────────────────────────────────────

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      className={`transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
      aria-hidden="true"
    >
      <path
        d="M4 6l4 4 4-4"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
