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

export interface MeetingWithCounts extends Meeting {
  agenda_item_count: number
  vote_count: number
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
}
