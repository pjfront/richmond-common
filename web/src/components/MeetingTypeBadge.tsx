'use client'

/**
 * MeetingTypeBadge — Design System Component (S14 A6)
 *
 * 3-channel accessible meeting type encoding:
 * - Color (background + text)
 * - Shape icon (circle, star, square, diamond)
 * - Text label
 *
 * Triple redundancy ensures accessibility across all color vision types.
 * Blue/Orange pair is the most universally distinguishable.
 */

import type { MeetingType } from '@/lib/types'
import CivicTerm from '@/components/CivicTerm'
import { CIVIC_GLOSSARY } from '@/data/civic-glossary'

interface MeetingTypeBadgeProps {
  /** Raw meeting_type string from database */
  meetingType: string
  /** Compact mode — icon + text only, no background */
  compact?: boolean
}

const MEETING_TYPE_CONFIG: Record<MeetingType, {
  label: string
  shape: string
  classes: string
  borderAccent: string
  glossarySlug: string
}> = {
  regular: {
    label: 'Regular',
    shape: '●',
    classes: 'bg-blue-50 text-blue-700 border-blue-200',
    borderAccent: 'border-l-blue-500',
    glossarySlug: 'meeting-regular',
  },
  special: {
    label: 'Special',
    shape: '★',
    classes: 'bg-orange-50 text-orange-700 border-orange-200',
    borderAccent: 'border-l-orange-500',
    glossarySlug: 'meeting-special',
  },
  closed_session: {
    label: 'Closed',
    shape: '■',
    classes: 'bg-purple-50 text-purple-700 border-purple-200',
    borderAccent: 'border-l-purple-500',
    glossarySlug: 'meeting-closed-session',
  },
  joint: {
    label: 'Joint',
    shape: '◆',
    classes: 'bg-teal-50 text-teal-700 border-teal-200',
    borderAccent: 'border-l-teal-500',
    glossarySlug: 'meeting-joint',
  },
}

/** Normalize database meeting_type strings to our MeetingType enum */
function normalizeMeetingType(raw: string): MeetingType {
  const lower = raw.toLowerCase().replace(/\s+/g, '_')
  if (lower.includes('special')) return 'special'
  if (lower.includes('closed')) return 'closed_session'
  if (lower.includes('joint')) return 'joint'
  return 'regular'
}

export default function MeetingTypeBadge({ meetingType, compact = false }: MeetingTypeBadgeProps) {
  const normalized = normalizeMeetingType(meetingType)
  const config = MEETING_TYPE_CONFIG[normalized]
  const glossary = CIVIC_GLOSSARY[config.glossarySlug]

  const label = glossary ? (
    <CivicTerm
      term={glossary.term}
      category={glossary.category}
      definition={glossary.definition}
    >
      {config.label}
    </CivicTerm>
  ) : (
    config.label
  )

  if (compact) {
    return (
      <span
        className={`inline-flex items-center gap-1 text-xs font-medium ${config.classes.split(' ').filter(c => c.startsWith('text-')).join(' ')}`}
      >
        <span aria-hidden="true">{config.shape}</span>
        {label}
      </span>
    )
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium rounded border ${config.classes}`}
    >
      <span aria-hidden="true">{config.shape}</span>
      {label}
    </span>
  )
}

/** Get the left border accent class for a meeting type (used on cards) */
export function getMeetingTypeBorderAccent(meetingType: string): string {
  const normalized = normalizeMeetingType(meetingType)
  return MEETING_TYPE_CONFIG[normalized].borderAccent
}

/** Get the normalized MeetingType from a raw database string */
export { normalizeMeetingType }
