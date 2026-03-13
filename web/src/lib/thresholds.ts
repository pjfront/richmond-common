/**
 * Confidence thresholds for conflict flag display.
 *
 * Three-tier system (v3 scanner, S9.6):
 *   Strong:   >= 0.85  (green-yellow-red badge: red)
 *   Moderate: >= 0.70  (green-yellow-red badge: yellow)
 *   Low:      >= 0.50  (green-yellow-red badge: green)
 *
 * The scanner (conflict_scanner.py) assigns publication tiers more
 * aggressively than the frontend displays. Defense-in-depth:
 *   Scanner publication_tier 1: >= 0.6  (catches more for review)
 *   Frontend "Strong":          >= 0.85 (only highest confidence shown in red)
 *
 * See docs/audits/2026-Q1-judgment-boundary-audit.md for rationale.
 * Threshold values are judgment calls (changing them requires operator approval).
 */

/** "Strong" (red badge). High-confidence pattern with multiple corroborating signals. */
export const CONFIDENCE_STRONG = 0.85

/** "Moderate" (yellow badge). Clear pattern with supporting evidence. */
export const CONFIDENCE_MODERATE = 0.70

/** "Low" (green badge). Possible pattern, limited evidence. */
export const CONFIDENCE_LOW = 0.50

/** Minimum confidence shown publicly. Flags below this are tracked internally only. */
export const CONFIDENCE_PUBLISHED = 0.50
