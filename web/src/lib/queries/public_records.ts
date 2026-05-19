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

// ─── Public Records (NextRequest/CPRA) ──────────────────────

export async function getPublicRecordsStats(
  cityFips = RICHMOND_FIPS
): Promise<PublicRecordsStats> {
  const { data, error } = await supabase
    .from('nextrequest_requests')
    .select('status, days_to_close, submitted_date')
    .eq('city_fips', cityFips)

  if (error) {
    console.error('getPublicRecordsStats query failed:', error)
    return { totalRequests: 0, avgResponseDays: 0, onTimeRate: 0, currentlyOverdue: 0 }
  }
  const requests = data ?? []

  const total = requests.length
  const completed = requests.filter((r) => r.days_to_close !== null)
  const avgDays = completed.length > 0
    ? Math.round(completed.reduce((sum, r) => sum + (r.days_to_close ?? 0), 0) / completed.length)
    : 0
  const onTime = completed.filter((r) => (r.days_to_close ?? 999) <= 10).length
  const onTimeRate = completed.length > 0
    ? Math.round((onTime / completed.length) * 100)
    : 0

  // Currently overdue: not closed AND more than 10 days since submitted
  // Status values from NextRequest API: "Closed", "Open", "Due soon" (case varies)
  const closedStatuses = new Set(['closed', 'completed'])
  const now = new Date()
  const overdue = requests.filter((r) => {
    if (closedStatuses.has((r.status || '').toLowerCase())) return false
    if (!r.submitted_date) return false
    const submitted = new Date(r.submitted_date + 'T00:00:00')
    const daysSince = Math.floor((now.getTime() - submitted.getTime()) / (1000 * 60 * 60 * 24))
    return daysSince > 10
  }).length

  return {
    totalRequests: total,
    avgResponseDays: avgDays,
    onTimeRate,
    currentlyOverdue: overdue,
  }
}

export async function getDepartmentCompliance(
  cityFips = RICHMOND_FIPS
): Promise<DepartmentCompliance[]> {
  const { data, error } = await supabase
    .from('nextrequest_requests')
    .select('department, days_to_close, status')
    .eq('city_fips', cityFips)

  if (error) {
    console.error('getDepartmentCompliance query failed:', error)
    return []
  }

  // Group by department
  const deptMap = new Map<string, { requests: typeof data }>()
  for (const r of data ?? []) {
    const dept = r.department || 'Unknown'
    const existing = deptMap.get(dept) ?? { requests: [] }
    existing.requests.push(r)
    deptMap.set(dept, existing)
  }

  return Array.from(deptMap.entries()).map(([dept, { requests }]) => {
    const completed = requests.filter((r) => r.days_to_close !== null)
    const avgDays = completed.length > 0
      ? Math.round(completed.reduce((sum, r) => sum + (r.days_to_close ?? 0), 0) / completed.length)
      : 0
    const onTime = completed.filter((r) => (r.days_to_close ?? 999) <= 10).length
    const onTimeRate = completed.length > 0 ? Math.round((onTime / completed.length) * 100) : 0
    const slowest = Math.max(...completed.map((r) => r.days_to_close ?? 0), 0)

    return {
      department: dept,
      requestCount: requests.length,
      avgDays,
      onTimeRate,
      slowestDays: slowest,
    }
  }).sort((a, b) => b.requestCount - a.requestCount)
}

export async function getRecentRequests(
  limit = 20,
  cityFips = RICHMOND_FIPS
): Promise<NextRequestRequest[]> {
  const { data, error } = await supabase
    .from('nextrequest_requests')
    .select(COLS_PUBLIC_RECORD_LIST)
    .eq('city_fips', cityFips)
    .order('submitted_date', { ascending: false })
    .limit(limit)

  if (error) {
    console.error('getRecentRequests query failed:', error)
    return [] as NextRequestRequest[]
  }
  return (data ?? []) as NextRequestRequest[]
}

export async function getAllPublicRecords(
  cityFips = RICHMOND_FIPS
): Promise<NextRequestRequest[]> {
  const { data, error } = await supabase
    .from('nextrequest_requests')
    .select(COLS_PUBLIC_RECORD_LIST)
    .eq('city_fips', cityFips)
    .order('submitted_date', { ascending: false })
    .range(0, 2499)

  if (error) {
    console.error('getAllPublicRecords query failed:', error)
    return [] as NextRequestRequest[]
  }
  return (data ?? []) as NextRequestRequest[]
}

