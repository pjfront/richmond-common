/**
 * Shared primitives for the queries module.
 *
 * Phase 2.4 of the 2026-05-09 re-architecture plan: extracted from the
 * top of the 5,607-LOC `queries.ts` god-file so domain modules
 * (`./meetings.ts`, `./council.ts`, ...) can `import { supabase, RICHMOND_FIPS,
 * COLS_MEETING_LIST } from './_shared'` without dragging each other in.
 *
 * Conventions:
 * - `COLS_*` are named select projections. Add columns here, not inline.
 *   Grep `COLS_` to audit coverage. Every domain query must use one rather
 *   than `select('*')` — keeps egress predictable, lets us strip heavy
 *   columns (raw_text, embeddings) from list views by default.
 * - Helpers (`warnIfEmpty`, `nameToSlug`, `isGovernmentEntity`,
 *   `filterGovernmentEntityFlags`) are exported here so multiple domain
 *   modules can use them without re-importing from `./index`.
 */
export { supabase } from '../supabase'

export const RICHMOND_FIPS = '0660620'

/**
 * Warn when a query that should always return data comes back empty.
 * Logs to stderr so it shows up in Vercel build/function logs.
 * Helps diagnose ISR cache poisoning from transient Supabase outages.
 */
export function warnIfEmpty(label: string, rows: unknown[] | null) {
  if (!rows || rows.length === 0) {
    console.warn(`[Richmond Commons] WARNING: "${label}" returned 0 rows — possible Supabase connectivity issue during build/ISR`)
  }
}

/** Compute URL slug from official name (officials table has no slug column) */
export function nameToSlug(name: string): string {
  return name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '')
}

/** Public alias of nameToSlug. Many callers import this as `officialToSlug`. */
export const officialToSlug = nameToSlug

/** Check if a name looks like a government entity (mirrors scanner's _is_government_entity) */
export function isGovernmentEntity(name: string): boolean {
  const norm = name.toLowerCase().trim()
  if (!norm) return false
  const prefixes = ['city of', 'city and county', 'city &', 'county of', 'state of', 'town of', 'district of', 'village of', 'borough of']
  const suffixes = [' county', ' city', ' state', ' department']
  return prefixes.some(p => norm.startsWith(p)) || suffixes.some(s => norm.endsWith(s))
}

/** Filter out conflict flags where the matched entity is a government entity.
 *  Two cases:
 *  1. donor_vendor_expenditure flags where the vendor is a government entity
 *  2. campaign_contribution/temporal_correlation flags where the match was
 *     employer-based (match_type starts with "employer_to_") and the employer
 *     is a government entity — e.g., "city of richmond" as employer matches
 *     every agenda item. The scanner now prevents these, but stale DB flags remain.
 *  Works on any array with evidence/flag_type. */
export function filterGovernmentEntityFlags<T extends { flag_type: string; evidence: Record<string, unknown>[] }>(flags: T[]): T[] {
  return flags.filter(f => {
    const ev = f.evidence?.[0]
    if (!ev) return true

    if (f.flag_type === 'donor_vendor_expenditure') {
      const vendor = ev.vendor
      if (typeof vendor === 'string' && isGovernmentEntity(vendor)) return false
    }

    const matchType = ev.match_type
    if (typeof matchType === 'string' && matchType.startsWith('employer_to_')) {
      const employer = ev.donor_employer
      if (typeof employer === 'string' && isGovernmentEntity(employer)) return false
    }

    return true
  })
}

// ─── Column Projections ────────────────────────────────────
// Named select shapes prevent select('*') drift and reduce egress.

/** Meeting columns for listing/card views (excludes metadata JSONB, description TEXT) */
export const COLS_MEETING_LIST = 'id, city_fips, document_id, body_id, meeting_date, meeting_type, call_to_order_time, adjournment_time, presiding_officer, minutes_url, agenda_url, video_url, adjourned_in_memory_of, next_meeting_date, meeting_summary, agenda_item_count, created_at'

/** Meeting columns for banner/CTA — minimal */
export const COLS_MEETING_BANNER = 'id, meeting_date, meeting_type, body_id, agenda_url'

/** Official-source fields for the public homepage meeting card. */
export const COLS_MEETING_FRONT_DOOR = 'id, meeting_date, meeting_type, agenda_url, source_meeting_guid, bodies(name)'

/** Source-closest active agenda observation for homepage freshness + link. */
export const COLS_FRONT_DOOR_SOURCE_DOCUMENT = 'ingested_at, source_url'

/** Election fields used by the public homepage and navigation. */
export const COLS_ELECTION_FRONT_DOOR = 'id, city_fips, election_date, election_name, election_type, filing_deadline, jurisdiction, notes, source, source_tier, source_url, created_at, updated_at'

/** Related-topic agenda cards plus the meeting fields used for recency and outcome labels. */
export const COLS_RELATED_TOPIC_ITEM = 'id, meeting_id, item_number, title, summary_headline, topic_label, category, financial_amount, public_comment_count, meetings!inner(meeting_date, city_fips, minutes_url)'

/** Complete official profile row. Named even though it is intentionally the
 *  full public row so a future schema addition cannot silently expand every
 *  cached profile read. */
export const COLS_OFFICIAL_FULL = 'id, city_fips, name, normalized_name, role, seat, term_start, term_end, is_current, party_affiliation, email, phone, bio_summary, bio_factual, bio_generated_at, bio_model, bio_summary_provenance, created_at'

/** Conflict flag columns for summary views (excludes description TEXT — loaded on-demand via /api/flag-details).
 *  evidence kept: needed by filterGovernmentEntityFlags() and ConflictFlagCard amber badge. */
export const COLS_FLAG_SUMMARY = 'id, city_fips, agenda_item_id, meeting_id, official_id, flag_type, evidence, confidence, legal_reference, reviewed, reviewed_at, reviewed_by, false_positive, is_current, created_at'

/** Public records columns for listing (excludes request_text, metadata JSONB) */
export const COLS_PUBLIC_RECORD_LIST = 'id, city_fips, request_number, requester_name, department, status, submitted_date, due_date, closed_date, days_to_close, document_count, portal_url, created_at, updated_at'

/** Contribution columns for public/operator listing views (excludes address,
 *  schedule, document_id, election_id — those are only needed in detail
 *  views or pipeline contexts). Includes contributor_type (set by
 *  src/contributor_classifier.py at load time) so the funding panel can
 *  bucket without re-classifying client-side. */
export const COLS_CONTRIBUTION_PUBLIC = 'id, amount, contribution_date, contribution_type, contributor_type, entity_code, filing_id, donor_id, committee_id, source, created_at'

/** Form 700 filing headers for council economic-interests sections (excludes
 *  metadata JSONB, filer_agency, document_id). Includes the D1 quartet
 *  (source_url, source_tier, confidence_score, extracted_at — migration 122)
 *  and no_interests_declared, which is a meaningful Tier 1 fact on its own. */
export const COLS_FORM700_FILING = 'id, city_fips, official_id, filer_name, filer_position, statement_type, period_start, period_end, filing_year, source, source_url, no_interests_declared, source_tier, confidence_score, extracted_at, created_at'
