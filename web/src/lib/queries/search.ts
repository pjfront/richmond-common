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
import { unstable_cache } from 'next/cache'
import {
  MAX_SIMILAR_ITEMS,
  SIMILAR_ITEMS_CACHE_SECONDS,
} from '../read-path-cache'
import { failReadPath } from '../read-path-unavailable'

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
    failReadPath('Site search', error)
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
    console.error('Hybrid search query failed; falling back to keyword search:', error)
    // A semantic-only failure can degrade safely. If keyword search also
    // fails, searchSite throws and the route returns an honest 503.
    return searchSite(query, options)
  }

  return (data ?? []) as SearchResult[]
}

const findSimilarItemsCached = unstable_cache(
  async (
    itemId: string,
    cityFips: string,
    limit: number,
  ): Promise<SimilarItem[]> => {
    const { data, error } = await supabase.rpc('find_similar_items', {
      p_item_id: itemId,
      p_city_fips: cityFips,
      p_limit: limit,
    })

    if (error) failReadPath('Similar discussions', error)

    return (data ?? []) as SimilarItem[]
  },
  ['similar-items-read-v1'],
  { revalidate: SIMILAR_ITEMS_CACHE_SECONDS },
)

export async function findSimilarItems(
  itemId: string,
  options?: {
    limit?: number
    cityFips?: string
  }
): Promise<SimilarItem[]> {
  const requestedLimit = options?.limit ?? 5
  const limit = Math.min(Math.max(1, requestedLimit), MAX_SIMILAR_ITEMS)
  return findSimilarItemsCached(
    itemId,
    options?.cityFips ?? RICHMOND_FIPS,
    limit,
  )
}

