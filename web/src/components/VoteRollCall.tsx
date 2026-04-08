'use client'

import { useState, useRef, useEffect } from 'react'
import type { MotionWithVotes, Vote } from '@/lib/types'
import ReportErrorLink from './ReportErrorLink'

/**
 * VoteRollCall — parliamentary roll-call grid for agenda item motions.
 *
 * Renders a shared header row (last names + legend), then each motion
 * as a compact row with aligned colored circles. Positions are fixed by
 * alphabetical last name, so voting patterns are scannable vertically
 * across motions.
 *
 * Accessibility (U2): five channels beyond color alone —
 *   1. Color (green/red/gray)
 *   2. Fill pattern (solid = voted, dashed outline = absent)
 *   3. Legend text ("● Aye  ● Nay" shown once)
 *   4. aria-label on each circle ("Soheila Bana — Aye")
 *   5. Tooltip on hover/focus with full name + vote
 */

// --- Vote normalization (shared with VoteBadge) ---

const VOTE_ALIASES: Record<string, string> = {
  noe: 'nay',
  no: 'nay',
  yes: 'aye',
  yea: 'aye',
}

function normalizeVoteChoice(choice: string): string {
  const lower = choice.toLowerCase()
  return VOTE_ALIASES[lower] ?? lower
}

// --- Roster derivation ---

interface RosterEntry {
  fullName: string
  lastName: string
  initials: string
  sortKey: string
}

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase()
  return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase()
}

function extractLastName(name: string): string {
  const parts = name.trim().split(/\s+/)
  return parts[parts.length - 1]
}

/**
 * Derive a stable roster from all votes across all motions.
 * Sorted alphabetically by last name. Works for any council composition.
 */
function deriveRoster(motions: MotionWithVotes[]): RosterEntry[] {
  const seen = new Map<string, RosterEntry>()
  for (const motion of motions) {
    for (const vote of motion.votes) {
      const lastName = extractLastName(vote.official_name)
      const sortKey = lastName.toLowerCase()
      if (!seen.has(sortKey)) {
        seen.set(sortKey, {
          fullName: vote.official_name,
          lastName,
          initials: getInitials(vote.official_name),
          sortKey,
        })
      }
    }
  }
  return Array.from(seen.values()).sort((a, b) => a.sortKey.localeCompare(b.sortKey))
}

/**
 * Map a motion's votes to roster positions. Returns one entry per roster slot
 * (null if that official didn't vote on this motion).
 */
function matchVotes(votes: Vote[], roster: RosterEntry[]): (Vote | null)[] {
  const byLastName = new Map<string, Vote>()
  for (const v of votes) {
    byLastName.set(extractLastName(v.official_name).toLowerCase(), v)
  }
  return roster.map(slot => byLastName.get(slot.sortKey) ?? null)
}

// --- Tally computation (carried from VoteBreakdown) ---

function computeTally(votes: Vote[]): string | null {
  if (votes.length === 0) return null
  const ayes = votes.filter(v => v.vote_choice === 'aye').length
  const nays = votes.filter(v => v.vote_choice === 'nay').length
  return `${ayes} to ${nays}`
}

// --- Circle styles ---

const CIRCLE_STYLES: Record<string, string> = {
  aye: 'bg-vote-aye text-white',
  nay: 'bg-vote-nay text-white',
  abstain: 'bg-vote-abstain text-white',
  absent: 'bg-white text-slate-300 border border-dashed border-slate-300',
}

const RING_STYLES: Record<string, string> = {
  aye: 'ring-vote-aye/50',
  nay: 'ring-vote-nay/50',
  abstain: 'ring-vote-abstain/50',
  absent: 'ring-slate-300',
}

// --- VoteCircle sub-component ---

function VoteCircle({ entry, vote }: { entry: RosterEntry; vote: Vote | null }) {
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState<'above' | 'below'>('below')
  const ref = useRef<HTMLSpanElement>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const choice = vote ? normalizeVoteChoice(vote.vote_choice) : 'absent'
  const label = choice.charAt(0).toUpperCase() + choice.slice(1)
  const tooltipText = `${entry.fullName} — ${label}`

  useEffect(() => {
    if (open && ref.current) {
      const rect = ref.current.getBoundingClientRect()
      const spaceBelow = window.innerHeight - rect.bottom
      setPosition(spaceBelow < 100 ? 'above' : 'below')
    }
  }, [open])

  const show = () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
    setOpen(true)
  }

  const hide = () => {
    timeoutRef.current = setTimeout(() => setOpen(false), 100)
  }

  return (
    <span className="relative inline-flex items-center justify-center w-9">
      <span
        ref={ref}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        tabIndex={0}
        aria-label={tooltipText}
        className={`w-9 h-9 rounded-full flex items-center justify-center text-[11px] font-bold cursor-default transition-all duration-150 ${
          CIRCLE_STYLES[choice] ?? CIRCLE_STYLES.absent
        } ${open ? `ring-2 ring-offset-2 scale-110 ${RING_STYLES[choice] ?? RING_STYLES.absent}` : ''}`}
      >
        {entry.initials}
      </span>

      {open && (
        <div
          role="tooltip"
          className={`absolute z-50 bg-white border border-slate-200 rounded-lg shadow-lg px-2.5 py-1.5 whitespace-nowrap ${
            position === 'above'
              ? 'bottom-full mb-2 left-1/2 -translate-x-1/2'
              : 'top-full mt-2 left-1/2 -translate-x-1/2'
          }`}
          onMouseEnter={show}
          onMouseLeave={hide}
        >
          <p className="text-xs text-slate-600">{tooltipText}</p>
        </div>
      )}
    </span>
  )
}

// --- Main component ---

export default function VoteRollCall({ motions }: { motions: MotionWithVotes[] }) {
  if (motions.length === 0) return null

  const roster = deriveRoster(motions)
  const hasAnyVotes = motions.some(m => m.votes.length > 0)

  return (
    <div className="space-y-4">
      {/* Header: last names + legend */}
      {hasAnyVotes && roster.length > 0 && (
        <div className="flex items-end justify-between" role="presentation" aria-hidden="true">
          <div className="flex gap-2">
            {roster.map(entry => (
              <div
                key={entry.sortKey}
                className="w-9 text-center text-[10px] font-medium text-slate-400 leading-tight"
                title={entry.fullName}
              >
                {entry.lastName}
              </div>
            ))}
          </div>
          <div className="flex items-center gap-3 text-[10px] text-slate-400 shrink-0 ml-3">
            <span className="inline-flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-vote-aye inline-block" />
              Aye
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-vote-nay inline-block" />
              Nay
            </span>
          </div>
        </div>
      )}

      {/* Motion rows */}
      {motions.map((motion) => {
        const resultColor = motion.result === 'passed'
          ? 'text-vote-aye'
          : motion.result === 'failed'
          ? 'text-vote-nay'
          : 'text-slate-600'

        const tally = computeTally(motion.votes)
        const mapped = matchVotes(motion.votes, roster)

        return (
          <div key={motion.id} className="border-t-2 border-slate-100 pt-3">
            {/* Motion text + result */}
            <div className="flex items-start justify-between gap-2 sm:gap-4">
              <p className="text-sm text-slate-700 break-words flex-1 min-w-0">
                {motion.motion_text}
              </p>
              <div className="text-right shrink-0">
                <span className={`font-semibold text-sm ${resultColor}`}>
                  {motion.result.charAt(0).toUpperCase() + motion.result.slice(1)}
                </span>
                {tally && (
                  <p className="text-xs text-slate-500 mt-0.5">{tally}</p>
                )}
              </div>
            </div>

            {/* Circle row — aligned with header */}
            {motion.votes.length > 0 && (
              <div className="flex gap-2 mt-2" role="group" aria-label="Individual votes">
                {mapped.map((vote, i) => (
                  <VoteCircle key={roster[i].sortKey} entry={roster[i]} vote={vote} />
                ))}
              </div>
            )}

            {/* Vote explainer (rare, preserved as-is) */}
            {motion.vote_explainer && (
              <div className="bg-blue-50 border border-blue-100 rounded-md p-3 mt-3">
                <p className="text-xs font-medium text-blue-600 mb-1">Why This Vote Matters</p>
                <p className="text-sm text-slate-700 leading-relaxed">
                  {motion.vote_explainer}
                </p>
                <p className="text-[10px] text-slate-400 mt-2">
                  Auto-generated context. Source: official meeting records.
                </p>
              </div>
            )}
          </div>
        )
      })}

      {/* Single error link for the section */}
      <div className="pt-1">
        <ReportErrorLink
          entityId={motions[0].id}
          entityType="motion"
          currentContext={motions.map(m => m.vote_tally ?? '').join('; ')}
        />
      </div>
    </div>
  )
}
