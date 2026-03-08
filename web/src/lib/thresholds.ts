/**
 * Confidence thresholds for conflict flag display.
 *
 * The scanner (conflict_scanner.py) assigns tiers more aggressively than the
 * frontend displays. This is intentional defense-in-depth:
 *   Scanner Tier 1: >= 0.6 (analysis boundary, catches more for review)
 *   Frontend Tier 1: >= 0.7 (publication boundary, only shows high confidence)
 *
 * See docs/audits/2026-Q1-judgment-boundary-audit.md for the full rationale.
 * Threshold values are judgment calls (changing them requires operator approval).
 */

/** "Potential Conflict" (red badge). High-confidence match. */
export const CONFIDENCE_TIER_1 = 0.7

/** "Financial Connection" (amber badge). Moderate-confidence match. */
export const CONFIDENCE_TIER_2 = 0.5

/** Minimum confidence shown publicly. Flags below this are tracked internally only. */
export const CONFIDENCE_PUBLISHED = 0.5
