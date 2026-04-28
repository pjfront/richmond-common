/**
 * Pure-text rendering helpers for Provenance structs.
 *
 * Used by email builders (lib/email.ts) where JSX isn't available. The
 * <SourceAttribution> component in components/SourceAttribution.tsx is
 * the JSX equivalent for in-page rendering. Both back onto the same
 * discriminated union — adding a new Provenance kind requires updating
 * both files (the TS compiler will tell you).
 *
 * Public-facing label wording is a judgment call (see
 * .claude/rules/judgment-boundaries.md). The strings below were lifted
 * from previously-shipped fixed strings (the Entry 51 audit on
 * 2026-04-27); changes to the wording need operator review.
 */

import type { Provenance } from './types'

const KCRT_URL = 'https://www.ci.richmond.ca.us/1604/KCRT-702'

/**
 * Map a public_comments.source value to a Provenance struct.
 *
 * Theme groupings are derived from public_comments at query time (no
 * stored *_provenance column), so the source-to-provenance mapping
 * happens here as a pure function. Used by both the server-side
 * candidate-vote query and any client component that needs to render
 * <ThemeAttribution> from a raw source string.
 */
export function commentSourceToProvenance(source: string | null): Provenance | null {
  if (!source) return null
  switch (source) {
    case 'youtube_transcript':
      return { kind: 'meeting_recording', channel: 'kcrt', as_of: '' }
    case 'granicus_transcript':
      return { kind: 'meeting_recording', channel: 'granicus', as_of: '' }
    case 'minutes':
      return { kind: 'official_minutes', minutes_url: null, as_of: '' }
    default:
      return null
  }
}

/**
 * Render the source phrase only, no surrounding text. Inline within
 * larger sentences. Mirrors the SourceLabel JSX primitive but as text.
 */
export function sourcePhrase(p: Provenance): string {
  switch (p.kind) {
    case 'official_minutes':
      return 'official minutes'
    case 'meeting_recording':
      return p.channel === 'kcrt'
        ? 'KCRT meeting recording'
        : 'meeting recording'
    case 'agenda_packet':
      return 'official agenda packet'
    case 'mixed':
      return 'official minutes and recent meeting recordings'
    case 'campaign_filing_period':
      return 'NetFile e-filings and extracted paper filings'
  }
}

/** Email recap footer — used by buildRecapEmail. */
export function recapAttributionText(p: Provenance): string {
  switch (p.kind) {
    case 'official_minutes':
      return 'This recap was auto-generated from official minutes and vote records.'
    case 'meeting_recording':
      return p.channel === 'kcrt'
        ? 'This recap was auto-generated from the KCRT meeting recording.'
        : 'This recap was auto-generated from the meeting recording.'
    case 'agenda_packet':
      // Recap from agenda packet alone is unusual but possible.
      return 'This recap was auto-generated from the official agenda packet.'
    case 'mixed':
      return `This recap was auto-generated from official minutes plus ${p.from_transcript} additional vote(s) extracted from the meeting recording while minutes are pending.`
    case 'campaign_filing_period':
      // Meeting recap should never carry a campaign-filing provenance.
      // Defensive fallback so the email builder doesn't crash.
      return 'This recap was auto-generated from official records.'
  }
}

/** Email orientation footer — used by buildOrientationEmail. */
export function orientationAttributionText(p: Provenance): string {
  // Orientation is always agenda_packet kind, but be defensive.
  switch (p.kind) {
    case 'agenda_packet':
      return 'This preview was auto-generated from the official agenda packet.'
    default:
      return `This preview was auto-generated from the ${sourcePhrase(p)}.`
  }
}

/**
 * Email digest footer — combines per-meeting provenance into a single
 * disclosure. Today's digest only ships official-minutes recaps (the
 * route filters for meeting_recap), so this collapses to the standard
 * line; the dispatch is here so a future change to the digest's input
 * source surfaces immediately rather than silently mislabeling.
 */
export function digestAttributionText(provenances: Provenance[]): string {
  if (provenances.length === 0) {
    return 'Recaps are auto-generated from official minutes and vote records.'
  }
  const kinds = new Set(provenances.map((p) => p.kind))
  if (kinds.size === 1) {
    const only = provenances[0]
    switch (only.kind) {
      case 'official_minutes':
        return 'Recaps are auto-generated from official minutes and vote records.'
      case 'meeting_recording':
        return 'Recaps are auto-generated from KCRT meeting recordings. Vote outcomes are preliminary until official minutes are published.'
      case 'agenda_packet':
        return 'Recaps are auto-generated from official agenda packets.'
      case 'mixed':
        return 'Recaps are auto-generated from official minutes and recent meeting recordings.'
      case 'campaign_filing_period':
        // Digest should never aggregate campaign briefings; defensive.
        return 'Recaps are auto-generated from official records.'
    }
  }
  // Mixed batch.
  return 'Recaps are auto-generated from a mix of official minutes and meeting recordings; per-meeting attribution is shown on each meeting page.'
}
