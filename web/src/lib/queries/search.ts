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

// ─── Site Search (S10.1) ────────────────────────────────────

export async function searchSite(
  query: string,
  options?: {
    resultType?: SearchResultType
    limit?: number
    offset?: number
    cityFips?: string
  }
): Promise<SearchResult[]> {
  const { data, error } = await supabase.rpc('search_site', {
    p_query: query,
    p_city_fips: options?.cityFips ?? RICHMOND_FIPS,
    p_result_type: options?.resultType ?? null,
    p_limit: options?.limit ?? 20,
    p_offset: options?.offset ?? 0,
  })

  if (error) {
    console.error('Search error:', error)
    return []
  }

  return (data ?? []) as SearchResult[]
}

// ─── Hybrid Search (S22) ────────────────────────────────────

export async function searchHybrid(
  query: string,
  queryEmbedding: number[] | null,
  options?: {
    resultType?: SearchResultType
    limit?: number
    offset?: number
    cityFips?: string
  }
): Promise<SearchResult[]> {
  const { data, error } = await supabase.rpc('search_hybrid', {
    p_query: query,
    p_query_embedding: queryEmbedding ? JSON.stringify(queryEmbedding) : null,
    p_city_fips: options?.cityFips ?? RICHMOND_FIPS,
    p_result_type: options?.resultType ?? null,
    p_limit: options?.limit ?? 20,
    p_offset: options?.offset ?? 0,
  })

  if (error) {
    console.error('Hybrid search error:', error)
    // Fallback to FTS-only
    return searchSite(query, options)
  }

  return (data ?? []) as SearchResult[]
}

export async function findSimilarItems(
  itemId: string,
  options?: {
    limit?: number
    cityFips?: string
  }
): Promise<SimilarItem[]> {
  const { data, error } = await supabase.rpc('find_similar_items', {
    p_item_id: itemId,
    p_city_fips: options?.cityFips ?? RICHMOND_FIPS,
    p_limit: options?.limit ?? 5,
  })

  if (error) {
    console.error('Similar items error:', error)
    return []
  }

  return (data ?? []) as SimilarItem[]
}

