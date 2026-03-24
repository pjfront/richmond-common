// TypeScript types matching the Supabase PostgreSQL schema (src/schema.sql)

export interface City {
  fips_code: string
  name: string
  state: string
  county: string | null
  population: number | null
  timezone: string
  charter_type: string | null
  website_url: string | null
  clerk_email: string | null
  council_size: number | null
  created_at: string
}

export interface Official {
  id: string
  city_fips: string
  name: string
  normalized_name: string
  role: string
  seat: string | null
  party_affiliation: string | null
  term_start: string | null
  term_end: string | null
  is_current: boolean
  email: string | null
  phone: string | null
  bio_factual: Record<string, unknown> | null
  bio_summary: string | null
  bio_generated_at: string | null
  bio_model: string | null
  created_at: string
}

export interface Meeting {
  id: string
  city_fips: string
  document_id: string | null
  body_id: string | null
  meeting_date: string
  meeting_type: string
  call_to_order_time: string | null
  adjournment_time: string | null
  presiding_officer: string | null
  minutes_url: string | null
  agenda_url: string | null
  video_url: string | null
  adjourned_in_memory_of: string | null
  next_meeting_date: string | null
  metadata: Record<string, unknown>
  created_at: string
}

export interface MeetingAttendance {
  id: string
  meeting_id: string
  official_id: string
  status: 'present' | 'absent' | 'late'
  notes: string | null
}

export interface AgendaItem {
  id: string
  meeting_id: string
  item_number: string
  title: string
  description: string | null
  department: string | null
  staff_contact: string | null
  category: string | null
  is_consent_calendar: boolean
  was_pulled_from_consent: boolean
  resolution_number: string | null
  financial_amount: string | null
  continued_from: string | null
  continued_to: string | null
  plain_language_summary: string | null
  summary_headline: string | null
  topic_label: string | null
  plain_language_generated_at: string | null
  plain_language_model: string | null
  created_at: string
}

export interface Motion {
  id: string
  agenda_item_id: string
  motion_type: string
  motion_text: string
  moved_by: string | null
  seconded_by: string | null
  result: string
  vote_tally: string | null
  resolution_number: string | null
  sequence_number: number
  vote_explainer: string | null
  vote_explainer_generated_at: string | null
  vote_explainer_model: string | null
  created_at: string
}

export interface Vote {
  id: string
  motion_id: string
  official_id: string | null
  official_name: string
  official_role: string | null
  vote_choice: 'aye' | 'nay' | 'abstain' | 'absent'
}

export interface Contribution {
  id: string
  city_fips: string
  donor_id: string
  committee_id: string
  amount: number
  contribution_date: string
  contribution_type: string
  filing_id: string | null
  schedule: string | null
  source: string
  document_id: string | null
  created_at: string
}

export interface Donor {
  id: string
  city_fips: string
  name: string
  normalized_name: string
  employer: string | null
  normalized_employer: string | null
  occupation: string | null
  address: string | null
  created_at: string
}

export interface Committee {
  id: string
  city_fips: string
  name: string
  filer_id: string | null
  committee_type: string | null
  candidate_name: string | null
  official_id: string | null
  status: string | null
  created_at: string
}

export interface ConflictFlag {
  id: string
  city_fips: string
  agenda_item_id: string | null
  meeting_id: string | null
  official_id: string | null
  flag_type: string
  description: string
  evidence: Record<string, unknown>[]
  confidence: number
  legal_reference: string | null
  reviewed: boolean
  reviewed_at: string | null
  reviewed_by: string | null
  false_positive: boolean | null
  created_at: string
}

export interface ClosedSessionItem {
  id: string
  meeting_id: string
  item_number: string
  legal_authority: string
  description: string
  parties: string[] | null
  reportable_action: string | null
}

export interface PublicComment {
  id: string
  meeting_id: string
  agenda_item_id: string | null
  speaker_name: string
  method: string
  summary: string | null
  comment_type: string
  submitted_by_system: boolean
  created_at: string
}

// Composite types for query results

export interface CategoryCount {
  category: string
  count: number
}

export interface MeetingWithCounts extends Meeting {
  agenda_item_count: number
  vote_count: number
  top_categories: CategoryCount[]
  all_categories: CategoryCount[]
}

export interface AgendaItemWithMotions extends AgendaItem {
  motions: MotionWithVotes[]
  /** Number of public comments on this item (0 if none or open forum) */
  public_comment_count: number
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

// ─── Economic Interests (Form 700) ─────────────────────────

export type InterestSchedule = 'A-1' | 'A-2' | 'B' | 'C' | 'D' | 'E'

export type InterestType =
  | 'real_property'
  | 'investment'
  | 'income'
  | 'gift'
  | 'business_position'

export interface EconomicInterest {
  id: string
  city_fips: string
  official_id: string | null
  filing_id: string | null
  filing_year: number
  schedule: InterestSchedule
  interest_type: InterestType
  description: string
  value_range: string | null
  location: string | null
  source_url: string | null
  // Joined from form700_filings
  statement_type: string | null
  period_start: string | null
  period_end: string | null
  filer_name: string | null
  filing_source: string | null
  filing_source_url: string | null
}

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

export interface UserFeedback {
  id: string
  city_fips: string
  feedback_type: FeedbackType
  entity_type: string | null
  entity_id: string | null
  flag_verdict: FlagVerdict | null
  field_name: string | null
  current_value: string | null
  suggested_value: string | null
  conflict_nature: string | null
  official_name: string | null
  description: string | null
  evidence_url: string | null
  evidence_text: string | null
  submitter_email: string | null
  submitter_name: string | null
  is_anonymous: boolean
  session_id: string | null
  status: FeedbackStatus
  created_at: string
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

export interface Body {
  id: string
  city_fips: string
  name: string
  body_type: BodyType
  short_name: string | null
  parent_body_id: string | null
  commission_id: string | null
  is_elected: boolean
  num_seats: number | null
  meeting_schedule: string | null
  is_active: boolean
  created_at: string
}

export interface BodyWithMeetingCounts extends Body {
  meeting_count: number
  first_meeting: string | null
  last_meeting: string | null
}

// ─── Commissions ─────────────────────────────────────────

export interface Commission {
  id: string
  city_fips: string
  name: string
  commission_type: string
  num_seats: number | null
  appointment_authority: string | null
  form700_required: boolean
  term_length_years: number | null
  meeting_schedule: string | null
  escribemeetings_type: string | null
  archive_center_amid: number | null
  website_roster_url: string | null
  last_website_scrape: string | null
  created_at: string
}

export interface CommissionMember {
  id: string
  city_fips: string
  commission_id: string
  name: string
  normalized_name: string
  role: string
  appointed_by: string | null
  appointed_by_official_id: string | null
  term_start: string | null
  term_end: string | null
  is_current: boolean
  source: string
  source_meeting_id: string | null
  website_stale_since: string | null
  created_at: string
  updated_at: string
}

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

export interface PendingDecision {
  id: string
  city_fips: string
  decision_type: DecisionType
  severity: DecisionSeverity
  title: string
  description: string
  evidence: Record<string, unknown>
  source: string
  entity_type: string | null
  entity_id: string | null
  link: string | null
  dedup_key: string | null
  status: DecisionStatus
  resolved_at: string | null
  resolved_by: string | null
  resolution_note: string | null
  created_at: string
  updated_at: string
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

export interface VotingBloc {
  members: Array<{ id: string; name: string }>
  category: string | null
  avg_mutual_agreement: number
  bloc_strength: 'strong' | 'moderate'
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

export interface SearchResult {
  id: string
  result_type: SearchResultType
  title: string
  snippet: string | null
  url_path: string
  relevance_score: number
  metadata: Record<string, unknown>
}

export interface SearchResponse {
  results: SearchResult[]
  query: string
  limit: number
  offset: number
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
  meeting_date: string
  category: string | null
  flag_count: number
  /** Whether this item had a split vote */
  has_split_vote: boolean
}

/** Full data bundle for the /influence/item/[id] page */
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

export interface Election {
  id: string
  city_fips: string
  election_date: string
  election_type: ElectionType
  election_name: string | null
  jurisdiction: string | null
  filing_deadline: string | null
  source: string
  source_url: string | null
  source_tier: number
  notes: string | null
  created_at: string
  updated_at: string
}

export interface ElectionCandidate {
  id: string
  city_fips: string
  election_id: string
  official_id: string | null
  candidate_name: string
  normalized_name: string
  office_sought: string
  party: string | null
  fppc_id: string | null
  committee_id: string | null
  status: CandidateStatus
  is_incumbent: boolean
  source: string
  source_url: string | null
  created_at: string
  updated_at: string
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
