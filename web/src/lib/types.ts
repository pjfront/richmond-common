// Hand-curated composite + view types. Row types for raw tables come from
// `./database.types.ts` (auto-generated via `npm run gen:types`). New code
// should prefer `Tables<'meetings'>` over hand-mirrored interfaces below;
// the hand-mirrored ones stay valid for backward compat until callers migrate.

export type { Database, Json } from './database.types'
import type { Database } from './database.types'
export type Tables<T extends keyof Database['public']['Tables']> =
  Database['public']['Tables'][T]['Row']
export type Inserts<T extends keyof Database['public']['Tables']> =
  Database['public']['Tables'][T]['Insert']
export type Updates<T extends keyof Database['public']['Tables']> =
  Database['public']['Tables'][T]['Update']
export type Views<T extends keyof Database['public']['Views']> =
  Database['public']['Views'][T]['Row']

// ── Provenance: provenance struct for auto-generated text artifacts ────
//
// Mirrors the JSONB columns added in migration 095 (*_provenance). Every
// auto-generated text artifact (recap, summary, bio) carries one of these
// describing what input source the generator actually used. Rendered via
// the <SourceAttribution> component — single source of truth for the
// "Auto-summarized from X" labels that previously lived as fixed strings
// scattered across components (Entry 51 dishonest-attribution audit).
//
// Adding a new variant: add to the union here, add a switch arm to
// SourceAttribution.tsx — the TS compiler tells you the rest.
//
// Discriminated by `kind`. `as_of` is when the generator wrote the row;
// `generator` and `backfilled` are diagnostic-only (never rendered).
export type Provenance =
  | {
      kind: 'official_minutes'
      minutes_url: string | null
      as_of: string
      generator?: string
      backfilled?: boolean
    }
  | {
      kind: 'meeting_recording'
      channel: 'kcrt' | 'granicus'
      as_of: string
      generator?: string
      backfilled?: boolean
    }
  | {
      kind: 'agenda_packet'
      agenda_url: string | null
      as_of: string
      generator?: string
      backfilled?: boolean
    }
  | {
      // Bio (or other aggregate) where the input set spans both
      // minutes-source and transcript-source motions. Counts must be
      // surfaced so the disclosure can be specific.
      kind: 'mixed'
      from_minutes: number
      from_transcript: number
      as_of: string
      generator?: string
      backfilled?: boolean
    }
  | {
      // Filing-period briefing (campaign-finance equivalent of meeting
      // recap). Counts are non-null so the renderer can disclose
      // evidence completeness; filed_through surfaces the lag between
      // period close and last actual filing — a missing-paper-filer
      // signal in itself.
      kind: 'campaign_filing_period'
      period_label: string
      contributions_count: number
      paper_filings_count: number
      filed_through: string | null
      as_of: string
      generator?: string
      backfilled?: boolean
    }


// ── Filing-period briefing (Stream 2 of 2026-04-28 plan) ───────────────
//
// Mirrors the Python build_briefing() output and the JSONB shape stored
// in filing_period_briefings.sections. Each section is independently
// tier-graded (A/B/C) per signal-significance-spec.md so the renderer
// can filter by readiness when promoting from Graduated to Public.

export type SectionTier = 'A' | 'B' | 'C'

export interface F1Totals {
  candidate_name: string
  office_sought: string
  committee_name: string | null
  fppc_id: string | null
  total_amount: number
  contribution_count: number
  unique_donors: number
  average_gift: number
  max_single_gift: number
}

export interface F2GeographyBuckets {
  richmond: number
  bay_area: number
  california_other: number
  out_of_state: number
  unknown: number
}

export interface F2Geography {
  candidate_name: string
  buckets_amount: F2GeographyBuckets
  buckets_share: F2GeographyBuckets
  total_amount: number
}

export interface F3IndustryPac {
  candidate_name: string
  pac_amount: number
  pac_share: number
  top_employers: Array<{ employer: string; amount: number }>
}

export interface F4SelfRelated {
  candidate_name: string
  self_funded_amount: number
  related_last_name_amount: number
  related_last_name_donors: string[]
}

export interface BriefingSection<T> {
  per_candidate?: Record<string, T>
  cross_race?: Record<string, unknown>
  tier?: SectionTier
  confidence?: number
  notes?: string[]
}

export interface FilingPeriodBriefingSections {
  F1_totals: BriefingSection<F1Totals>
  F2_geography: BriefingSection<F2Geography>
  F3_industry_pac: BriefingSection<F3IndustryPac>
  F4_self_related: BriefingSection<F4SelfRelated>
  // F5..F9 stubs — present in the JSONB but not rendered yet
  F5_donor_clustering?: BriefingSection<unknown>
  F6_deadline_burst?: BriefingSection<unknown>
  F7_compliance?: BriefingSection<unknown>
  F8_vendor_employee?: BriefingSection<unknown>
  F9_levine_exposure?: BriefingSection<unknown>
}

// Anchored to generated `filing_period_briefings` Row. Narrows the four
// JSONB columns (sections, section_tiers, provenance) to typed shapes
// and publication_tier string to literal union. Anchor auto-adds
// generator-metadata columns (generator, generator_version, model_version,
// superseded_at) absent from hand-rolled.
export interface FilingPeriodBriefing extends Omit<
  Tables<'filing_period_briefings'>,
  'sections' | 'section_tiers' | 'provenance' | 'publication_tier'
> {
  sections: FilingPeriodBriefingSections
  section_tiers: Partial<Record<keyof FilingPeriodBriefingSections, SectionTier>>
  provenance: Provenance | null
  publication_tier: 'public' | 'operator' | 'graduated'
}

// ── PAC profile (public, graduated S28.4) ──────────────────────────────
//
// A "PAC" here = any `committees` row with `official_id IS NULL` — i.e.,
// not a candidate-controlled committee. Includes general-purpose PACs,
// IE committees, ballot-measure committees, and union/employer-sponsored
// committees. The `kind` discriminator surfaces the substantive shape
// (sponsor disclosure for public-prose, e.g. "funded by Chevron Richmond"
// for Coalition for Richmond's Future). Inferred from name prefix until
// migration 088-style sponsor field lands.
export interface PACAggregate {
  /** Canonical committees.id (UUID). When multiple rows share a real
   *  filer_id we collapse them at the query layer; this is the canonical
   *  row's id, picked by longest name. Use `member_ids` for any query
   *  that should fan across the entire merged set. */
  id: string
  /** All underlying committees.id rows that collapse into this one PAC
   *  (canonical id always included). For most committees this is just
   *  `[id]`; for filer_ids that surfaced under multiple name variants
   *  it includes all member rows. */
  member_ids: string[]
  /** Display name verbatim from filing */
  name: string
  /** Short slug derived from name + filer_id (when available) */
  slug: string
  /** NetFile/CAL-ACCESS filer ID — null for "Pending" or unfiled */
  filer_id: string | null
  /** committees.committee_type — values vary; treat as advisory */
  committee_type: string | null
  /** Inferred sponsor for prose disclosure ("funded by X", "Sponsored by Y") */
  sponsor_disclosure: string | null
  /** Total raised across all years */
  total_raised: number
  /** Distinct donor count */
  donor_count: number
  /** Total contribution rows (incl. duplicates pre-dedup) */
  contribution_count: number
  /** Latest contribution date observed */
  latest_contribution_date: string | null
  /** Earliest contribution date observed */
  earliest_contribution_date: string | null
}

export interface PACContributionRow {
  donor_name: string
  donor_employer: string | null
  amount: number
  contribution_date: string
  contribution_type: string | null
  filing_id: string | null
}

export interface PACOutgoingRow {
  /** Recipient committee name (i.e., where this PAC's money landed) */
  recipient_committee_name: string
  /** Recipient committee_id when matched, else null */
  recipient_committee_id: string | null
  /** Recipient candidate name when known (committees.candidate_name) */
  recipient_candidate_name: string | null
  amount: number
  contribution_date: string
  contribution_type: string | null
  filing_id: string | null
}

// ─── Organization Profiles (S28.3) ──────────────────────────────────

/** One org entity (union or corporation donor) for the /orgs index.
 *  Multiple donor rows with the same entity_slug are collapsed into
 *  one aggregate row at the query layer. */
export interface OrgAggregate {
  /** entity_slug — URL-safe, stable across name variants */
  slug: string
  /** Longest donor.name among the merged donor rows */
  display_name: string
  /** 'union' | 'corporation' */
  entity_type: string
  /** All donor.id rows that collapse into this org */
  donor_ids: string[]
  /** Sum of all donors.total_contributed across member rows (all-time) */
  total_contributed: number
  /** Total contributed in the current election cycle (e.g. 2025-01-01 through today).
   *  Computed from contributions table, not donors.total_contributed.
   *  This is the primary sort key for listing pages. */
  current_cycle_total: number
  /** Approximate distinct recipient count */
  recipient_count: number
  /** Earliest contribution date from the contributions table */
  earliest_contribution_date: string | null
  /** Latest contribution date from the contributions table */
  latest_contribution_date: string | null
  /** Mandatory disclosure per source-tier rules (e.g. Chevron) */
  sponsor_disclosure: string | null
}

/** One contribution FROM an org (as donor) TO a committee.  Same shape
 *  as PACOutgoingRow — an org profile is just a donor-centric view of
 *  the same contribution records. */
export interface OrgOutgoingRow {
  /** Committee that received the money */
  recipient_committee_name: string
  /** Committee id for linking */
  recipient_committee_id: string | null
  /** Candidate name when the recipient is a candidate committee */
  recipient_candidate_name: string | null
  amount: number
  contribution_date: string
  contribution_type: string | null
  filing_id: string | null
}

// ─── Individual Donor Profiles (S28.6) ──────────────────────────────

/** One individual donor for the /donors index.
 *  entity_type = 'person', total_contributed >= $5,000. */
export interface DonorProfile {
  /** entity_slug — URL-safe identifier */
  slug: string
  /** Donor display name */
  display_name: string
  /** Donor's employer (if known) */
  employer: string | null
  /** Donor's occupation (if known) */
  occupation: string | null
  /** The donor.id for this profile */
  donor_id: string
  /** Aggregate total contributed across all cycles (all-time) */
  total_contributed: number
  /** Total contributed in the current election cycle (e.g. 2025-01-01 through today).
   *  Computed from contributions table. Primary sort key for listing. */
  current_cycle_total: number
  /** Number of distinct recipient committees */
  recipient_count: number
  /** Earliest contribution date on file */
  earliest_contribution_date: string | null
  /** Latest contribution date on file */
  latest_contribution_date: string | null
}

/** One contribution FROM an individual donor TO a committee. */
export interface DonorOutgoingRow {
  /** Committee that received the money */
  recipient_committee_name: string
  /** Committee id for linking */
  recipient_committee_id: string | null
  /** Candidate name when the recipient is a candidate committee */
  recipient_candidate_name: string | null
  amount: number
  contribution_date: string
  contribution_type: string | null
  filing_id: string | null
}

/** Independent expenditure: a PAC spending money to support or oppose a
 *  candidate WITHOUT donating to the candidate's campaign. Required FPPC
 *  disclosure on Form 460 Schedule D / Form 496 / CAL-ACCESS EXPN_CD.
 *  This is the influence-flow data that PACContributionRow + PACOutgoingRow
 *  miss for committees that spend directly on mailers, ads, and canvassing
 *  rather than transferring funds to other committees. */
export interface PACIndependentExpenditureRow {
  /** Candidate this expenditure supported or opposed. May also name a
   *  recipient committee for PAC-to-PAC transfers, or null for ballot
   *  measures and untargeted spending. */
  candidate_name: string | null
  /** 'S' = support, 'O' = oppose. May be null in ambiguous source rows. */
  support_or_oppose: 'S' | 'O' | null
  amount: number
  expenditure_date: string
  /** Vendor or recipient of the spend (mailer printer, ad agency, etc.) */
  payee_name: string | null
  /** Free-text from the filing: typically a description of the expenditure. */
  description: string | null
  /** CAL-ACCESS expenditure code: IND, LIT, MTG, PRO, etc. */
  expenditure_code: string | null
  /** Filing source identifier; used for traceability. */
  filing_id: string | null
}

// Pure mirror of generated `cities` Row.
export type City = Tables<'cities'>

// Anchored to generated `officials` Row. Narrows JSONB columns
// (bio_factual, bio_summary_provenance) to typed shapes.
export interface Official extends Omit<
  Tables<'officials'>,
  'bio_factual' | 'bio_summary_provenance'
> {
  bio_factual: Record<string, unknown> | null
  bio_summary_provenance: Provenance | null
}

// Anchored to the generated `meetings` Row. Overrides narrow JSON columns
// to typed shapes. (`body_id` confirmed NOT NULL in DB, zero null rows —
// hand-rolled previously typed it `string | null` in error.)
export interface Meeting extends Omit<
  Tables<'meetings'>,
  | 'meeting_summary_provenance'
  | 'meeting_recap_provenance'
  | 'orientation_preview_provenance'
  | 'transcript_recap_provenance'
  | 'metadata'
> {
  meeting_summary_provenance: Provenance | null
  meeting_recap_provenance: Provenance | null
  orientation_preview_provenance: Provenance | null
  transcript_recap_provenance: Provenance | null
  metadata: Record<string, unknown>
}

// Anchored to generated `meeting_attendance` Row. Narrows `status` to
// its known literal union. Anchor auto-adds `body_id` (newly present in
// schema, absent from hand-rolled).
export interface MeetingAttendance extends Omit<Tables<'meeting_attendance'>, 'status'> {
  status: 'present' | 'absent' | 'late'
}

// Anchored to generated `agenda_items` Row. Narrows JSONB
// `plain_language_summary_provenance` to typed shape. Anchor adds
// auto-included columns: legal_framework, legal_framework_classified_at,
// legal_framework_source, party_entities, discussion_duration_minutes
// (all previously absent from hand-rolled).
export interface AgendaItem extends Omit<
  Tables<'agenda_items'>,
  'plain_language_summary_provenance'
> {
  plain_language_summary_provenance: Provenance | null
}

// Anchored to generated `motions` Row. Narrows `source` string to its
// known literal union and asserts non-null (DB column is nullable per
// generator, but every query filters by source IS NOT NULL).
export interface Motion extends Omit<Tables<'motions'>, 'source'> {
  /**
   * Origin of this motion record:
   *   'minutes'    — extracted from official minutes PDF (ground truth, 4-6 wk lag)
   *   'transcript' — preliminary, parsed from transcript_recap (1-3 day lag)
   * UI surfaces a "Tentative" badge for transcript-sourced motions.
   */
  source: 'minutes' | 'transcript'
}

// Anchored to generated `votes` Row. Narrows `vote_choice` and `source`
// string columns to their known literal unions; asserts source non-null
// (parallels Motion — every query filters source IS NOT NULL).
export interface Vote extends Omit<Tables<'votes'>, 'vote_choice' | 'source'> {
  vote_choice: 'aye' | 'nay' | 'abstain' | 'absent' | 'yes' | 'no'
  source: 'minutes' | 'transcript'
}

// Pure mirror of generated `contributions` Row. Anchor adds auto-included
// columns: contributor_type, contributor_type_source, election_id,
// entity_code (all previously absent from hand-rolled).
export type Contribution = Tables<'contributions'>

// Pure mirror of generated `donors` Row. Anchor adds the donor-pattern
// columns (contribution_span_days, distinct_recipients, donor_pattern,
// total_contributed) that hand-rolled was missing.
export type Donor = Tables<'donors'>

// Pure mirror of generated `committees` Row. Anchor adds `election_id`
// that hand-rolled was missing.
export type Committee = Tables<'committees'>

// Anchored to generated `conflict_flags` Row. Narrows JSONB columns:
//   - `evidence` to typed array
//   - `confidence_factors` to scanner-output shape (consumed by
//     ConflictFlagCard.tsx — `temporal_direction` is the load-bearing
//     field; rest preserved as `unknown` extension)
// Anchor auto-adds scanner-metadata columns (data_cutoff_date,
// is_current, match_details, publication_tier, scan_mode, scan_run_id,
// scanner_version) absent from hand-rolled.
export interface ConflictFlag extends Omit<
  Tables<'conflict_flags'>,
  'evidence' | 'confidence_factors'
> {
  evidence: Record<string, unknown>[]
  confidence_factors: {
    temporal_direction?: 'pre_vote' | 'post_vote' | 'mixed'
    [key: string]: unknown
  } | null
}

// Pure mirror of generated `closed_session_items` Row.
export type ClosedSessionItem = Tables<'closed_session_items'>

// Pure mirror of generated `public_comments` Row. Anchor auto-adds
// confidence, extracted_at, name_confidence, source columns absent from
// hand-rolled.
export type PublicComment = Tables<'public_comments'>

// Composite types for query results

export interface CategoryCount {
  category: string
  count: number
}

export interface TopicLabelCount {
  label: string
  count: number
}

export interface MeetingWithCounts extends Meeting {
  vote_count: number
  top_categories: CategoryCount[]
  all_categories: CategoryCount[]
  top_topic_labels: TopicLabelCount[]
  all_topic_labels: TopicLabelCount[]
}

export interface NotableSpeaker {
  name: string
  role: string
}

export interface CommentSummary {
  total: number
  notable_speakers: NotableSpeaker[]
}

export interface AgendaItemWithMotions extends AgendaItem {
  motions: MotionWithVotes[]
  /** Number of public comments on this item (0 if none or open forum) */
  public_comment_count: number
  /** Aggregated comment summary with notable speaker detection */
  comment_summary?: CommentSummary
  /** Theme narratives for inline community voice display */
  theme_narratives?: ThemeNarrative[]
  /** Number of speakers at the meeting for this item */
  spoken_comment_count?: number
  /** Number of written comments for this item */
  written_comment_count?: number
  /** Source of comment data (youtube_transcript, granicus_transcript, minutes) */
  comment_source?: string | null
}

export interface MotionWithVotes extends Motion {
  votes: Vote[]
}

export interface MeetingDetail extends Meeting {
  agenda_items: AgendaItemWithMotions[]
  attendance: (MeetingAttendance & { official: Pick<Official, 'name' | 'role'> })[]
  closed_session_items: ClosedSessionItem[]
  /** Total public comments across all items in this meeting */
  total_public_comments: number
}

// ─── Agenda Item Detail Page ────────────────────────────────

/** Public comment with full detail for the item detail page */
export interface PublicCommentDetail {
  id: string
  speaker_name: string
  method: string        // 'in_person' | 'zoom' | 'phone' | 'email' | 'ecomment'
  comment_type: string  // 'public' | 'written'
  summary: string | null
  /** Whether the speaker is a current or former official */
  is_notable: boolean
  /** e.g. "councilmember", "former mayor" */
  notable_role?: string
  /** Theme slug from comment_theme_assignments, if clustered */
  theme_slug?: string
  /** Confidence of theme assignment */
  theme_confidence?: number
}

/** Theme extracted from public comments (topic, not sentiment).
 * Lightweight projection of `comment_themes` row — Pick<> instead of full
 * row keeps the DTO small while preserving drift detection (renamed/dropped
 * columns from this list still fail to compile). */
export type CommentTheme = Pick<
  Tables<'comment_themes'>,
  'id' | 'slug' | 'label' | 'description'
>

/** Lightweight comment for operator-only theme drill-down */
export interface ThemeComment {
  speaker_name: string
  method: string
  comment_type: string
}

/** AI-generated narrative for a theme on a specific agenda item */
export interface ThemeNarrative {
  theme: CommentTheme
  narrative: string
  comment_count: number
  confidence: number
  generated_at: string
  /** Speakers at meeting for this theme (computed server-side) */
  spoken_count?: number
  /** Written comments for this theme (computed server-side) */
  written_count?: number
  /** Individual comments for operator drill-down */
  comments?: ThemeComment[]
}

/** Minimal item reference for continued_from/continued_to links */
export interface AgendaItemRef {
  id: string
  meeting_id: string
  item_number: string
  title: string
  meeting_date: string
}

/** Sibling item in the same meeting for prev/next navigation */
export interface AgendaItemSibling {
  item_number: string
  summary_headline: string | null
  title: string
}

/** Related item sharing topic label and/or category */
export interface RelatedTopicItem {
  id: string
  meeting_id: string
  item_number: string
  title: string
  summary_headline: string | null
  topic_label: string
  category: string | null
  meeting_date: string
  financial_amount: string | null
  public_comment_count: number
  /** 1 = same topic + category, 2 = same topic only, 3 = same category only */
  match_tier: 1 | 2 | 3
  /** Simplified vote outcome */
  vote_outcome: 'passed' | 'failed' | 'no vote' | 'upcoming' | 'minutes pending'
}

/** Full item detail for the /meetings/[id]/items/[itemNumber] page */
export interface AgendaItemDetail extends AgendaItemWithMotions {
  /** Parent meeting context */
  meeting_date: string
  meeting_type: string
  meeting_agenda_url: string | null
  meeting_minutes_url: string | null
  /** Full comment records, grouped by type */
  comments: PublicCommentDetail[]
  written_comment_count: number
  spoken_comment_count: number
  /** Theme narratives for this item (empty if not yet extracted) */
  theme_narratives: ThemeNarrative[]
  /** Source of comment data: 'youtube_transcript' | 'minutes' */
  comment_source: string | null
  /** When comments were extracted */
  comment_extracted_at: string | null
  /** Conflict flags meeting the publication threshold */
  conflict_flags: ConflictFlag[]
  /** Linked items if this was continued from/to another meeting */
  continued_from_item: AgendaItemRef | null
  continued_to_item: AgendaItemRef | null
  /** Previous item in agenda order (same meeting) */
  prev_item: AgendaItemSibling | null
  /** Next item in agenda order (same meeting) */
  next_item: AgendaItemSibling | null
  /** Items sharing the same topic label, sorted by date */
  related_topic_items: RelatedTopicItem[]
}

// ─── Official Stats ─────────────────────────────────────────

export interface OfficialWithStats extends Official {
  vote_count: number
  attendance_rate: number
}

export interface DonorAggregate {
  donor_name: string
  donor_employer: string | null
  total_amount: number
  contribution_count: number
  source: string
  donor_pattern: string | null
}

/** Individual contribution for client-side date filtering on council profiles */
export interface DonorContribution {
  donor_name: string
  donor_employer: string | null
  donor_pattern: string | null
  amount: number
  contribution_date: string
  source: string
}

// ─── Economic Interests (Form 700) ─────────────────────────

export type InterestSchedule = 'A-1' | 'A-2' | 'B' | 'C' | 'D' | 'E'

export type InterestType =
  | 'real_property'
  | 'investment'
  | 'income'
  | 'gift'
  | 'business_position'
  | 'travel'

// Anchored to generated `economic_interests` Row. Narrows schedule +
// interest_type strings to literal unions. Composite: also includes
// fields joined from `form700_filings` at query time (statement_type,
// period_*, filer_*, filing_source*).
export interface EconomicInterest extends Omit<
  Tables<'economic_interests'>,
  'schedule' | 'interest_type'
> {
  schedule: InterestSchedule
  interest_type: InterestType
  // Joined from form700_filings
  statement_type: string | null
  period_start: string | null
  period_end: string | null
  filer_name: string | null
  filing_source: string | null
  filing_source_url: string | null
}

// Anchored to generated `form700_filings` Row — projection of
// COLS_FORM700_FILING (queries/_shared.ts). Filing header incl. the
// "no reportable interests" flag, which is a meaningful Tier 1 fact
// even when a filing has zero interest line items.
export type Form700Filing = Pick<
  Tables<'form700_filings'>,
  | 'id'
  | 'city_fips'
  | 'official_id'
  | 'filer_name'
  | 'filer_position'
  | 'statement_type'
  | 'period_start'
  | 'period_end'
  | 'filing_year'
  | 'source'
  | 'source_url'
  | 'no_interests_declared'
  | 'source_tier'
  | 'confidence_score'
  | 'extracted_at'
  | 'created_at'
>

// ─── User Feedback ──────────────────────────────────────────

export type FeedbackType =
  | 'flag_accuracy'
  | 'data_correction'
  | 'tip'
  | 'missing_conflict'
  | 'general'

export type FlagVerdict = 'confirm' | 'dispute' | 'add_context'

export type FeedbackStatus =
  | 'pending'
  | 'reviewing'
  | 'accepted'
  | 'rejected'
  | 'duplicate'
  | 'acted_on'

// Anchored to generated `user_feedback` Row. Narrows feedback_type +
// flag_verdict + status strings to literal unions. Anchor auto-adds
// action_entity_id, action_taken, moderator_notes, page_url, reviewed_*,
// updated_at columns absent from hand-rolled.
export interface UserFeedback extends Omit<
  Tables<'user_feedback'>,
  'feedback_type' | 'flag_verdict' | 'status'
> {
  feedback_type: FeedbackType
  flag_verdict: FlagVerdict | null
  status: FeedbackStatus
}

export interface FeedbackSubmission {
  feedback_type: FeedbackType
  city_fips?: string
  entity_type?: string
  entity_id?: string
  flag_verdict?: FlagVerdict
  field_name?: string
  current_value?: string
  suggested_value?: string
  conflict_nature?: string
  official_name?: string
  description?: string
  evidence_url?: string
  evidence_text?: string
  submitter_email?: string
  submitter_name?: string
  page_url?: string
}

export interface FeedbackResponse {
  success: boolean
  reference_id: string | null
  error?: string
}

// ─── Data Freshness ─────────────────────────────────────────

export interface DataSourceFreshness {
  source: string
  last_sync: string | null
  threshold_days: number
  days_since_sync: number | null
  is_stale: boolean
}

// ─── NextRequest / CPRA ─────────────────────────────────────

export interface NextRequestRequest {
  id: string
  city_fips: string
  request_number: string
  request_text: string
  requester_name: string | null
  department: string | null
  status: string
  submitted_date: string | null
  due_date: string | null
  closed_date: string | null
  days_to_close: number | null
  document_count: number
  portal_url: string | null
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface PublicRecordsStats {
  totalRequests: number
  avgResponseDays: number
  onTimeRate: number
  currentlyOverdue: number
}

export interface DepartmentCompliance {
  department: string
  requestCount: number
  avgDays: number
  onTimeRate: number
  slowestDays: number
}

// ─── Governing Bodies ────────────────────────────────────

export type BodyType = 'city_council' | 'commission' | 'board' | 'authority' | 'committee' | 'joint'

// Anchored to generated `bodies` Row. Narrows `body_type` string to
// `BodyType` literal union.
export interface Body extends Omit<Tables<'bodies'>, 'body_type'> {
  body_type: BodyType
}

export interface BodyWithMeetingCounts extends Body {
  meeting_count: number
  first_meeting: string | null
  last_meeting: string | null
}

// ─── Commissions ─────────────────────────────────────────

// Pure mirror of generated `commissions` Row.
export type Commission = Tables<'commissions'>

// Pure mirror of generated `commission_members` Row.
export type CommissionMember = Tables<'commission_members'>

export interface CommissionWithStats extends Commission {
  member_count: number
  holdover_count: number
  vacancy_count: number
}

export interface CommissionStaleness {
  commission_id: string
  city_fips: string
  commission_name: string
  last_website_scrape: string | null
  stale_members: number
  total_current_members: number
  oldest_stale_since: string | null
  max_days_stale: number | null
  stale_member_names: string[] | null
}

// ─── Operator Decision Queue (S7) ────────────────────────────

export type DecisionType =
  | 'staleness_alert'
  | 'anomaly'
  | 'tier_graduation'
  | 'conflict_review'
  | 'assessment_finding'
  | 'pipeline_failure'
  | 'general'

export type DecisionSeverity = 'critical' | 'high' | 'medium' | 'low' | 'info'

export type DecisionStatus = 'pending' | 'approved' | 'rejected' | 'deferred'

// Anchored to generated `pending_decisions` Row. Narrows decision_type +
// severity + status strings to literal unions; narrows JSONB evidence to
// typed record (preserves existing non-null assumption — DB allows null
// per generator).
export interface PendingDecision extends Omit<
  Tables<'pending_decisions'>,
  'decision_type' | 'severity' | 'status' | 'evidence'
> {
  decision_type: DecisionType
  severity: DecisionSeverity
  status: DecisionStatus
  evidence: Record<string, unknown>
}

export interface DecisionQueueResponse {
  summary: {
    total_pending: number
    counts: Record<DecisionSeverity, number>
  }
  pending: PendingDecision[]
  recently_resolved: PendingDecision[]
}

// ─── Data Quality ───────────────────────────────────────────

export interface MeetingCompleteness {
  meeting_id: string
  meeting_date: string
  meeting_type: string
  agenda_item_count: number
  vote_count: number
  attendance_count: number
  has_minutes: boolean
  has_agenda: boolean
  has_video: boolean
  completeness_score: number
}

export interface DocumentCoverage {
  count: number
  percentage: number
}

export interface DataAnomaly {
  meeting_id: string
  meeting_date: string
  anomaly_type: string
  description: string
  severity: 'warning' | 'alert'
}

export interface DataQualityResponse {
  freshness: {
    sources: DataSourceFreshness[]
    stale_count: number
    total: number
  }
  completeness: {
    total_meetings: number
    complete_meetings: number
    document_coverage: {
      minutes: DocumentCoverage
      agenda: DocumentCoverage
      video: DocumentCoverage
    }
    recent_meetings: MeetingCompleteness[]
  }
  anomalies: DataAnomaly[]
  overall_status: 'healthy' | 'warning' | 'alert'
  checked_at: string
}

// ─── Pattern Detection (S6) ─────────────────────────────────

export interface CategoryStats {
  category: string
  item_count: number
  vote_count: number
  split_vote_count: number
  unanimous_vote_count: number
  avg_controversy_score: number
  max_controversy_score: number
  total_public_comments: number
  percentage_of_agenda: number
}

export interface ControversyItem {
  agenda_item_id: string
  meeting_id: string
  meeting_date: string
  item_number: string
  title: string
  category: string | null
  controversy_score: number
  vote_tally: string | null
  result: string
  public_comment_count: number
  motion_count: number
}

// ─── Coalition / Voting Alignment (S6.1) ────────────────────

export interface PairwiseAlignment {
  official_a_id: string
  official_a_name: string
  official_b_id: string
  official_b_name: string
  category: string | null       // null = overall
  agreement_count: number
  disagreement_count: number
  total_shared_votes: number
  agreement_rate: number         // 0.0 to 1.0
}

export interface CategoryDivergence {
  official_a_id: string
  official_a_name: string
  official_b_id: string
  official_b_name: string
  overall_agreement_rate: number
  category: string
  category_agreement_rate: number
  divergence_gap: number          // overall - category rate
  shared_category_votes: number
}

// ─── Divergent Motions (per-motion vote breakdown) ──────────

/**
 * One row per (motion, official) pair from get_divergent_motions_detail RPC.
 * Frontend groups by motion_id to render member-vs-motion tables.
 * Includes both contested-aye/nay voters and absent/abstaining members for
 * the same motion so the table can show every member's stance per row.
 */
export interface DivergentMotionRow {
  motion_id: string
  motion_text: string | null
  motion_result: string | null
  vote_tally: string | null
  meeting_id: string
  meeting_date: string
  agenda_item_id: string
  agenda_item_title: string
  agenda_item_number: string | null
  category: string | null
  topic_label: string | null
  is_procedural: boolean
  official_id: string
  official_name: string
  vote_choice: 'aye' | 'nay' | 'abstain' | 'absent'
}

/**
 * Grouped form: one entry per motion with a votes map keyed by official_id.
 * Built client-side from DivergentMotionRow[] for table rendering.
 */
export interface DivergentMotion {
  motion_id: string
  motion_text: string | null
  motion_result: string | null
  vote_tally: string | null
  meeting_id: string
  meeting_date: string
  agenda_item_id: string
  agenda_item_title: string
  agenda_item_number: string | null
  category: string | null
  topic_label: string | null
  is_procedural: boolean
  votes: Record<string, 'aye' | 'nay' | 'abstain' | 'absent'>  // official_id -> choice
}

// ─── Cross-Meeting Patterns (S6.2) ─────────────────────────

export interface DonorCategoryPattern {
  donor_id: string
  donor_name: string
  donor_employer: string | null
  donor_pattern: string | null
  total_contributed: number
  recipient_count: number
  top_category: string
  category_concentration: number   // 0.0 to 1.0
  category_breakdown: Array<{ category: string; vote_count: number }>
}

// ─── Financial Connections (S10.4) ──────────────────────────

export interface FinancialConnectionFlag {
  id: string
  flag_type: string
  confidence: number
  description: string
  evidence: Record<string, unknown>[]
  // Joined meeting context
  meeting_id: string
  meeting_date: string
  // Joined agenda item context
  agenda_item_id: string
  agenda_item_title: string
  agenda_item_number: string
  agenda_item_category: string | null
  // Vote correlation (from motions → votes join)
  vote_choice: 'aye' | 'nay' | 'abstain' | 'absent' | null
  motion_result: string | null
  is_unanimous: boolean | null
}

export interface OfficialConnectionSummary {
  official_id: string
  official_name: string
  official_slug: string
  total_flags: number
  voted_in_favor: number
  voted_against: number
  abstained: number
  absent_for: number
  no_vote_recorded: number
  flag_type_breakdown: Record<string, number>
  flags: FinancialConnectionFlag[]
}

export interface DonorOverlap {
  donor_id: string
  donor_name: string
  donor_employer: string | null
  total_contributed: number
  recipients: Array<{
    official_id: string
    official_name: string
    amount: number
    contribution_count: number
  }>
}

// ─── Meeting & Entity Types (S14) ───────────────────────────

export type MeetingType = 'regular' | 'special' | 'closed_session' | 'joint'

export type EntityType = 'agenda_item' | 'official' | 'donor' | 'meeting'

// ─── Site Search (S10.1) ────────────────────────────────────

export type SearchResultType = 'agenda_item' | 'official' | 'vote_explainer' | 'meeting'

export type SearchMatchType = 'keyword' | 'semantic' | 'both'

export interface SearchResult {
  id: string
  result_type: SearchResultType
  title: string
  snippet: string | null
  url_path: string
  relevance_score: number
  match_type: SearchMatchType
  metadata: Record<string, unknown>
}

export interface SearchResponse {
  results: SearchResult[]
  query: string
  limit: number
  offset: number
}

// ─── Similar Discussions (S22) ──────────────────────────────

export interface SimilarItem {
  id: string
  title: string
  summary_headline: string | null
  meeting_id: string
  meeting_date: string
  item_number: string
  similarity: number
  vote_outcome: 'passed' | 'failed' | 'upcoming' | 'minutes pending' | 'no vote'
  public_comment_count: number
  financial_amount: string | null
  category: string | null
  topic_label: string | null
}

// ─── Influence Map (S14-C) ──────────────────────────────────

/** A single contribution record with contextual data for narrative display */
export interface ContributionRecord {
  contribution_id: string
  donor_name: string
  donor_employer: string | null
  committee_name: string
  official_name: string
  official_id: string
  official_slug: string
  amount: number
  contribution_date: string
  source: string         // 'netfile', 'calaccess'
  filing_id: string | null
}

/** Aggregated contribution context for one official × one donor on an agenda item */
export interface ContributionNarrativeData {
  official_id: string
  official_name: string
  official_slug: string
  donor_name: string
  donor_employer: string | null
  /** Total contributed from this donor to this official */
  total_contributed: number
  /** Number of individual contribution records */
  contribution_count: number
  /** Date range of contributions */
  earliest_date: string
  latest_date: string
  /** Official's total fundraising from all donors */
  official_total_fundraising: number
  /** This donor's contributions as % of total fundraising */
  percentage_of_fundraising: number
  /** How this official voted on this agenda item */
  vote_choice: string | null
  /** How many other members voted the same way */
  same_way_voter_count: number
  /** How many of those same-way voters had no contributions from this donor */
  same_way_without_contribution: number
  /** Confidence score from the conflict flag */
  confidence: number
  /** Source tier label */
  source_tier: string
  /** Date of the most recent filing */
  source_date: string
  /** Individual contribution records */
  contributions: ContributionRecord[]
  /** Source URL for the filing */
  source_url: string | null
  /** Flag type from conflict scanner */
  flag_type: string
  /** Flag description */
  flag_description: string
  /** Vendor expenditure total (for donor_vendor_expenditure flags) */
  vendor_expenditure_total?: number
  /** Vendor expenditure count (for donor_vendor_expenditure flags) */
  vendor_expenditure_count?: number
  /** Entity name when different from donor (e.g., org name for llc_ownership_chain) */
  entity_name?: string
  /** Relationship type (e.g., 'employer', 'organization', 'direct') */
  entity_relationship?: string
}

/** Behested payment record for influence map display */
export interface BehstedPaymentNarrativeData {
  id: string
  official_name: string
  official_id: string | null
  payor_name: string
  payee_name: string
  payee_description: string | null
  amount: number | null
  payment_date: string | null
  filing_date: string | null
  source_url: string | null
  /** Whether this payor is also a campaign contributor to this official */
  is_also_contributor: boolean
  /** Total contributions from this payor if also a contributor */
  contributor_total: number | null
}

/** Vote context for displaying on influence map */
export interface ItemVoteContext {
  official_id: string
  official_name: string
  official_slug: string
  vote_choice: string
  motion_result: string
}

/** Related agenda item (same entities involved) */
export interface RelatedAgendaItem {
  id: string
  title: string
  summary_headline: string | null
  meeting_id: string
  /** Meeting-scoped item number ("H-1", "I.3", etc.). Required so consumers can
   *  build canonical agenda-item URLs via agendaItemPath(). Added 2026-05-13
   *  in Phase 2.6 alongside the /influence/item route consolidation. */
  item_number: string
  meeting_date: string
  category: string | null
  flag_count: number
  /** Whether this item had a split vote */
  has_split_vote: boolean
}

/** Full data bundle for <InfluenceMapItemSection> on the canonical agenda-item page */
export interface ItemInfluenceMapData {
  /** The agenda item itself */
  item: {
    id: string
    title: string
    item_number: string
    description: string | null
    plain_language_summary: string | null
    summary_headline: string | null
    category: string | null
    financial_amount: string | null
    is_consent_calendar: boolean
    was_pulled_from_consent: boolean
    resolution_number: string | null
    meeting_id: string
    meeting_date: string
  }
  /** All votes on this item */
  votes: ItemVoteContext[]
  /** Campaign contribution narratives grouped by official × donor */
  contributions: ContributionNarrativeData[]
  /** Behested payment records linked to this item's entities */
  behested_payments: BehstedPaymentNarrativeData[]
  /** Other agenda items involving the same entities */
  related_items: RelatedAgendaItem[]
  /** Total number of conflict flags on this item */
  total_flags: number
  /** Source URLs for metadata */
  source_url: string | null
  extracted_at: string | null
}

// ── Election Cycle Tracking (B.24) ────────────────────────

export type ElectionType = 'primary' | 'general' | 'special' | 'runoff'

export type CandidateStatus = 'filed' | 'qualified' | 'withdrawn' | 'elected' | 'defeated'

// Anchored to generated `elections` Row. Narrows election_type string
// to ElectionType literal union.
export interface Election extends Omit<Tables<'elections'>, 'election_type'> {
  election_type: ElectionType
}

// Anchored to generated `election_candidates` Row. Narrows status string
// to CandidateStatus literal union. Anchor auto-adds qualification_date
// absent from hand-rolled.
export interface ElectionCandidate extends Omit<Tables<'election_candidates'>, 'status'> {
  status: CandidateStatus
}

export interface ElectionWithCandidates extends Election {
  candidates: ElectionCandidate[]
}

export interface CandidateFundraising {
  candidate_name: string
  office_sought: string
  is_incumbent: boolean
  status: CandidateStatus
  total_raised: number
  contribution_count: number
  donor_count: number
  avg_contribution: number
  largest_contribution: number
  smallest_contribution: number
}

export interface CandidateTopDonor {
  donor_name: string
  employer: string | null
  total_contributed: number
  contribution_count: number
}

export interface CandidateDonorsByCycle {
  cycleDonors: CandidateTopDonor[]
  priorDonors: CandidateTopDonor[]
  cycleLabel: string // e.g. "Jan 2025 – Jun 2026"
}

// ── Candidate funding breakdown (operator-only, S24 funding artifact) ──
//
// Powers /elections/[slug]/mayor/funding. Aggregates a candidate-
// controlled committee's incoming contributions by contributor_type
// (set at load time by src/contributor_classifier.py) so the panel can
// surface "from individual donors" vs "from union PACs" vs "from
// for-profit corporations" without inferring types client-side.

export type ContributorTypeBucket = 'individual' | 'union' | 'corporate' | 'pac_ie' | 'other'

export interface CandidateFundingBucket {
  contributor_type: ContributorTypeBucket
  contribution_count: number
  total_amount: number
  /** Top entities within this bucket (e.g., for "union" bucket: top union PACs by amount). */
  top_donors: Array<{ name: string; total: number; count: number }>
}

export interface CandidateFundingBreakdown {
  committee_id: string
  total_raised: number
  contribution_count: number
  donor_count: number
  last_contribution_date: string | null
  /** max(contributions.created_at) — drives the "Updated X ago" badge. */
  last_updated_at: string | null
  /** Sorted by total_amount desc. */
  buckets: CandidateFundingBucket[]
}

// One IE supporter committee surfaced on the candidate's funding panel.
// Combines two source streams: contributions INTO an IE committee
// (committee.name pattern "supporting [candidate]") and IEs SPENT by any
// committee whose independent_expenditures.candidate_name matches.
export interface CandidateIESupporter {
  /** Committee id when we matched it via committees.name. Null when the
   *  IE supporter only appears in independent_expenditures (no funding
   *  contributions yet matched to a known committee row). */
  ie_committee_id: string | null
  ie_committee_name: string
  /** 'S' if the IE supports the candidate, 'O' if it opposes. Inferred
   *  from independent_expenditures.support_or_oppose; defaults to 'S'
   *  for committees matched only by "supporting [name]" naming. */
  support_or_oppose: 'S' | 'O' | null
  /** Money raised INTO the IE committee (Schedule A on the IE's own
   *  filings). For Anderson's Safe Richmond Neighborhoods, this captures
   *  the $30K POA seed contribution that hasn't been spent yet. */
  ie_funds_raised: number
  ie_funds_raised_count: number
  ie_top_funders: Array<{ name: string; total: number }>
  /** Money SPENT by the IE on materials supporting or opposing the
   *  candidate (independent_expenditures rows). */
  ie_funds_spent: number
  ie_funds_spent_count: number
  /** Most recent date across either funding-in or spending-out. */
  latest_activity_date: string | null
}

// ── Contribution bucket matrix (5 amount × 4 source-type) ─────────
//
// Replaces the older ContributionBreakdown (small/medium/large/major
// keyed on convenient round numbers) with a matrix keyed on California
// campaign-finance regulatory thresholds verified in D56b (parking lot,
// 2026-05-17). Each amount bucket is named after the rule that makes
// crossing the boundary meaningful, not after a marketing label.
//
// The matrix is intentionally a DTO (type alias, not interface) — it
// doesn't mirror a Postgres table, so the types.drift.test.ts safeguard
// shouldn't try to anchor it to Tables<>. The bucket boundaries are
// also exposed at runtime via lib/contributionBuckets.ts so that the
// test suite + the methodology page + the query function all stay
// consistent.

/**
 * Amount-bucket keys. Each boundary is a real California campaign-
 * finance rule, NOT an arbitrary round number. See docs/AI-PARKING-LOT.md
 * D56b for primary sources, and /elections/methodology for the public
 * plain-language explanation.
 *
 *  - `under_100`        : below FPPC $100 itemization threshold
 *  - `between_100_249`  : itemized but below SB 1439 ($250) pay-to-play
 *  - `between_250_999`  : SB 1439 territory (pending-business recusal)
 *  - `between_1000_2499`: Form 497 24-hour late-contribution trigger
 *  - `at_2500_cap`      : Richmond MC 2.42.050(a)(1) per-cycle cap
 */
export type ContributionBucketKey =
  | 'under_100'
  | 'between_100_249'
  | 'between_250_999'
  | 'between_1000_2499'
  | 'at_2500_cap'

/**
 * Source-type keys. Mapped from contributions.contributor_type
 * (`individual` / `corporate` / `union` / `pac_ie` / `other`) — see
 * migration 048 + src/contributor_classifier.py. `other` rolls into
 * `business` in display per the same convention CAL-ACCESS ENTITY_CD
 * 'OTH' uses ("Other" is overwhelmingly businesses; the few non-business
 * Others get the same plain-language label).
 */
export type ContributorTypeKey = 'individual' | 'business' | 'union' | 'pac'

export interface ContributionMatrixCell {
  count: number
  dollars: number
}

/**
 * Dense 5×4 matrix. Every (source, bucket) cell is always present, even
 * when empty (count=0, dollars=0). Callers don't need optional-chaining.
 */
export interface ContributionMatrix {
  cells: Record<ContributorTypeKey, Record<ContributionBucketKey, ContributionMatrixCell>>
  total_count: number
  total_dollars: number
}

export interface CandidateFundraisingDetail extends CandidateFundraising {
  id: string                        // election_candidates.id — joins to filing_period_briefings.sections per_candidate
  committee_id: string | null
  official_id: string | null
  top_donors: CandidateTopDonor[]
  contribution_matrix: ContributionMatrix
  // True when the headline total_raised (Form 460 cover) and the sum of
  // matrix cells agree to within $1. False when there's a material drift —
  // typically Form 497 late-filings not yet rolled into a Form 460, or
  // paper-filing reconciliation gaps. CandidateCard hides the bucket grid
  // when false to avoid showing a headline number that doesn't match the
  // breakdown sum. Set by getCandidateFundraisingDetails in queries/elections.ts.
  bucket_grid_consistent: boolean
  earliest_contribution: string | null
  latest_contribution: string | null
  lifetime_raised: number
}

// ── Operator Config (migration 074) ──────────────────────────

export interface OperatorPublication {
  tier_high: number
  tier_medium: number
  tier_low: number
  hedge_enabled: boolean
  hedge_text: string
  blocklist: string[]
}

export interface OperatorEvidence {
  match_strength: number
  temporal_factor: number
  financial_factor: number
  anomaly_factor: number
  sitting_mult: number
  non_sitting_mult: number
  corroboration_2: number
  corroboration_3plus: number
}

export interface OperatorTemporalBand {
  days: number
  factor: number
}

export interface OperatorTemporal {
  bands: OperatorTemporalBand[]
  beyond_factor: number
  post_vote_penalty: number
  anomaly_boost_days: number
  anomaly_boost_amount: number
}

export interface OperatorFinancialBand {
  min: number
  factor: number
}

export interface OperatorQuality {
  weight_items: number
  weight_votes: number
  weight_attendance: number
  weight_urls: number
  anomaly_stddev: number
  min_baselines: number
  default_anomaly: number
}

// Editable subset of generated `operator_config` Row — the operator UI
// renders/edits the five JSONB-shaped knobs and `updated_at`, not the
// row-identity columns (id, city_fips, updated_by). Pick<> from the
// generated row keeps the safeguard active: if any of these column
// names get renamed/dropped in a migration, the type stops compiling.
export type OperatorConfig = Omit<
  Pick<
    Tables<'operator_config'>,
    'publication' | 'evidence' | 'temporal' | 'financial' | 'quality' | 'updated_at'
  >,
  'publication' | 'evidence' | 'temporal' | 'financial' | 'quality'
> & {
  publication: OperatorPublication
  evidence: OperatorEvidence
  temporal: OperatorTemporal
  financial: OperatorFinancialBand[]
  quality: OperatorQuality
}

// ─── Email Subscription ───────────────────────────────────

// Anchored to generated `email_subscribers` Row. Narrows status + source
// string columns to literal unions, narrows metadata Json to typed record
// (preserves existing non-null assumption — DB allows null but no callsite
// handles null today; flag for audit).
export interface EmailSubscriber extends Omit<
  Tables<'email_subscribers'>,
  'status' | 'source' | 'metadata'
> {
  status: 'active' | 'unsubscribed'
  source: 'website' | 'manual'
  metadata: Record<string, unknown>
}

export interface SubscribeRequest {
  email: string
  name?: string
}

export interface SubscribeResponse {
  success: boolean
  message: string
}

// ─── Email Preferences ──────────────────────────────────

export type PreferenceType = 'topic' | 'district' | 'candidate'

// Anchored to generated `email_preferences` Row. Narrows preference_type
// string column to literal union.
export interface EmailPreference extends Omit<
  Tables<'email_preferences'>,
  'preference_type'
> {
  preference_type: PreferenceType
}

export interface SubscriptionPreferences {
  topics: string[]
  districts: string[]
  candidates: string[]
}

export interface PreferencesResponse {
  success: boolean
  preferences?: SubscriptionPreferences
  error?: string
}

// Anchored to generated `neighborhood_councils` Row. Preserves existing
// non-null assumption on created_at/updated_at (DB allows null per
// generator but every callsite treats them as non-null; flag for audit).
export interface NeighborhoodCouncil extends Omit<
  Tables<'neighborhood_councils'>,
  'created_at' | 'updated_at'
> {
  created_at: string
  updated_at: string
}
