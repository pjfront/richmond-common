/**
 * Deterministic color assignment for topic labels.
 * Same label always gets the same color across all surfaces.
 *
 * When a topic label matches a local issue name, the local issue's
 * canonical color is used instead of the hash — so filter pills and
 * inline badges stay visually consistent.
 */

import { RICHMOND_LOCAL_ISSUES } from './local-issues'

/** Local issue label → color, built once at module load */
const LOCAL_ISSUE_COLORS: Record<string, string> = {}
for (const issue of RICHMOND_LOCAL_ISSUES) {
  LOCAL_ISSUE_COLORS[issue.label.toLowerCase()] = issue.color
}

const LABEL_COLORS = [
  'bg-blue-100 text-blue-700',
  'bg-emerald-100 text-emerald-700',
  'bg-amber-100 text-amber-700',
  'bg-purple-100 text-purple-700',
  'bg-rose-100 text-rose-700',
  'bg-cyan-100 text-cyan-700',
  'bg-lime-100 text-lime-700',
  'bg-orange-100 text-orange-700',
  'bg-sky-100 text-sky-700',
  'bg-pink-100 text-pink-700',
  'bg-teal-100 text-teal-700',
  'bg-indigo-100 text-indigo-700',
]

function hashString(s: string): number {
  let hash = 0
  for (let i = 0; i < s.length; i++) {
    hash = ((hash << 5) - hash + s.charCodeAt(i)) | 0
  }
  return Math.abs(hash)
}

export function topicLabelColor(label: string): string {
  // Prefer canonical local issue color when the label matches
  const localColor = LOCAL_ISSUE_COLORS[label.toLowerCase()]
  if (localColor) return localColor
  return LABEL_COLORS[hashString(label) % LABEL_COLORS.length]
}
