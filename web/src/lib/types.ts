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
}

export interface MotionWithVotes extends Motion {
  votes: Vote[]
}

export interface MeetingDetail extends Meeting {
  agenda_items: AgendaItemWithMotions[]
  attendance: (MeetingAttendance & { official: Pick<Official, 'name' | 'role'> })[]
  closed_session_items: ClosedSessionItem[]
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
