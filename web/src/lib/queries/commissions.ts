import { fetchMeetingCounts, applyMeetingCounts } from './meetings'
import {
  supabase,
  RICHMOND_FIPS,
  warnIfEmpty,
  nameToSlug,
  isGovernmentEntity,
  filterGovernmentEntityFlags,
  COLS_MEETING_LIST,
  COLS_MEETING_BANNER,
  COLS_FLAG_SUMMARY,
  COLS_PUBLIC_RECORD_LIST,
} from './_shared'
import RICHMOND_FILERS_DATA from '@/data/netfile-richmond-filers.json'
import type {
  Meeting,
  Official,
  AgendaItem,
  Motion,
  Vote,
  MeetingAttendance,
  ConflictFlag,
  ClosedSessionItem,
  NotableSpeaker,
  AgendaItemWithMotions,
  MotionWithVotes,
  MeetingDetail,
  DonorAggregate,
  DonorContribution,
  EconomicInterest,
  NextRequestRequest,
  PublicRecordsStats,
  DepartmentCompliance,
  Commission,
  CommissionMember,
  CommissionWithStats,
  CommissionStaleness,
  CategoryStats,
  ControversyItem,
  PairwiseAlignment,
  CategoryDivergence,
  DivergentMotionRow,
  DivergentMotion,
  DonorCategoryPattern,
  DonorOverlap,
  CategoryCount,
  TopicLabelCount,
  MeetingWithCounts,
  FinancialConnectionFlag,
  OfficialConnectionSummary,
  SearchResult,
  SearchResultType,
  SimilarItem,
  ContributionNarrativeData,
  ContributionRecord,
  BehstedPaymentNarrativeData,
  ItemVoteContext,
  RelatedAgendaItem,
  ItemInfluenceMapData,
  Election,
  ElectionCandidate,
  ElectionWithCandidates,
  CandidateFundraising,
  CandidateFundraisingDetail,
  CandidateTopDonor,
  CandidateDonorsByCycle,
  ContributionBreakdown,
  PublicCommentDetail,
  CommentTheme,
  ThemeNarrative,
  AgendaItemDetail,
  AgendaItemRef,
  AgendaItemSibling,
  RelatedTopicItem,
  CommunityComment,
  NeighborhoodCouncil,
  Provenance,
  FilingPeriodBriefing,
  PACAggregate,
  PACContributionRow,
  PACOutgoingRow,
  PACIndependentExpenditureRow,
} from '../types'
import { CONFIDENCE_PUBLISHED } from '../thresholds'
import { commentSourceToProvenance } from '../provenance'

// ─── Commissions ─────────────────────────────────────────

export async function getCommissions(
  cityFips = RICHMOND_FIPS
): Promise<CommissionWithStats[]> {
  const { data: commissions, error } = await supabase
    .from('commissions')
    .select('*')
    .eq('city_fips', cityFips)
    .order('name')

  if (error) {
    console.error('getCommissions query failed:', error)
    return [] as CommissionWithStats[]
  }
  warnIfEmpty('getCommissions', commissions)

  const commissionIds = (commissions ?? []).map((c) => c.id)
  if (commissionIds.length === 0) return []

  // Count current members per commission, separating active-term from holdovers
  const { data: members } = await supabase
    .from('commission_members')
    .select('commission_id, term_end')
    .in('commission_id', commissionIds)
    .eq('is_current', true)

  const today = new Date().toISOString().split('T')[0]
  const activeCountMap = new Map<string, number>()
  const holdoverCountMap = new Map<string, number>()
  for (const m of members ?? []) {
    const isExpired = m.term_end && m.term_end < today
    if (isExpired) {
      holdoverCountMap.set(m.commission_id, (holdoverCountMap.get(m.commission_id) ?? 0) + 1)
    } else {
      activeCountMap.set(m.commission_id, (activeCountMap.get(m.commission_id) ?? 0) + 1)
    }
  }

  return (commissions ?? []).map((c) => {
    const commission = c as Commission
    const activeCount = activeCountMap.get(commission.id) ?? 0
    const holdoverCount = holdoverCountMap.get(commission.id) ?? 0
    const vacancyCount = commission.num_seats
      ? Math.max(0, commission.num_seats - activeCount)
      : 0
    return {
      ...commission,
      member_count: activeCount,
      holdover_count: holdoverCount,
      vacancy_count: vacancyCount,
    }
  })
}

export async function getCommission(
  commissionId: string,
  cityFips = RICHMOND_FIPS
): Promise<{ commission: Commission; members: CommissionMember[] } | null> {
  const { data: commission, error } = await supabase
    .from('commissions')
    .select('*')
    .eq('id', commissionId)
    .eq('city_fips', cityFips)
    .single()

  if (error || !commission) return null

  const { data: members } = await supabase
    .from('commission_members')
    .select('*')
    .eq('commission_id', commissionId)
    .eq('is_current', true)
    .order('name')

  return {
    commission: commission as Commission,
    members: (members ?? []) as CommissionMember[],
  }
}

export async function getCommissionStaleness(
  cityFips = RICHMOND_FIPS
): Promise<CommissionStaleness[]> {
  const { data, error } = await supabase
    .from('v_commission_staleness')
    .select('*')
    .eq('city_fips', cityFips)

  if (error) {
    console.error('getCommissionStaleness query failed:', error)
    return [] as CommissionStaleness[]
  }
  return (data ?? []) as CommissionStaleness[]
}

export async function getCommissionMeetings(
  commissionId: string,
  cityFips = RICHMOND_FIPS
): Promise<MeetingWithCounts[]> {
  // Step 1: Find the body linked to this commission
  const { data: body } = await supabase
    .from('bodies')
    .select('id')
    .eq('commission_id', commissionId)
    .eq('city_fips', cityFips)
    .single()

  if (!body) return []

  // Step 2: Fetch meetings for this body + counts (with RPC fallback)
  const [{ data: meetings, error }, countMap] = await Promise.all([
    supabase
      .from('meetings')
      .select(COLS_MEETING_LIST)
      .eq('body_id', body.id)
      .eq('city_fips', cityFips)
      .order('meeting_date', { ascending: false }),
    fetchMeetingCounts(cityFips),
  ])

  if (error || !meetings) return []

  return applyMeetingCounts(meetings as Meeting[], countMap)
}


// ─── Neighborhood Councils ─────────────────────────────────────────────────

const COLS_NEIGHBORHOOD_COUNCIL =
  'id, city_fips, name, short_name, nc_type, geojson_codes, is_active, ' +
  'meeting_schedule, meeting_time, meeting_location, city_page_url, ' +
  'city_page_id, document_center_path, contact_email, president, ' +
  'vice_president, notes, created_at, updated_at'

export async function getNeighborhoodCouncils(
  cityFips = RICHMOND_FIPS
): Promise<NeighborhoodCouncil[]> {
  const { data, error } = await supabase
    .from('neighborhood_councils')
    .select(COLS_NEIGHBORHOOD_COUNCIL)
    .eq('city_fips', cityFips)
    .order('name')

  if (error) {
    console.error('getNeighborhoodCouncils query failed:', error)
    return []
  }
  return (data ?? []) as unknown as NeighborhoodCouncil[]
}
