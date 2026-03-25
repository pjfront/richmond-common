/**
 * Shared display formatting utilities.
 *
 * Centralizes snake_case → display string conversions so compound terms
 * like "quasi-judicial" render correctly instead of naively splitting
 * on underscores.
 */

// ─── URL Helpers ────────────────────────────────────────────

/**
 * Build the canonical path for an agenda item detail page.
 * Item numbers are meeting-scoped (e.g. "H-1"), so the path nests under the meeting.
 */
export function agendaItemPath(meetingId: string, itemNumber: string): string {
  return `/meetings/${meetingId}/items/${encodeURIComponent(itemNumber.toLowerCase())}`
}

// ─── Display Formatting ─────────────────────────────────────

/** Known compound terms that need hyphens instead of spaces */
const COMPOUND_TERMS: Record<string, string> = {
  quasi_judicial: 'Quasi-Judicial',
}

/** Format a commission_type value for display */
export function formatCommissionType(type: string): string {
  if (COMPOUND_TERMS[type]) return COMPOUND_TERMS[type]
  return type
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}
