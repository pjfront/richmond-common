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

// ─── Community Comments ────────────────────────────────────

/**
 * Fetch published community comments for an agenda item, threaded.
 * Returns top-level comments with nested replies.
 */
export async function getCommunityComments(
  agendaItemId: string,
  cityFips: string = RICHMOND_FIPS,
): Promise<CommunityComment[]> {
  const { data, error } = await supabase
    .from('community_comments')
    .select('id, city_fips, agenda_item_id, parent_comment_id, author_name, comment_text, status, submitted_to_clerk, created_at, updated_at')
    .eq('agenda_item_id', agendaItemId)
    .eq('city_fips', cityFips)
    .eq('status', 'published')
    .order('created_at', { ascending: true })

  if (error || !data) return []

  const comments = data as CommunityComment[]

  // Thread: group replies under parents
  const topLevel: CommunityComment[] = []
  const replyMap = new Map<string, CommunityComment[]>()

  for (const c of comments) {
    if (c.parent_comment_id) {
      const existing = replyMap.get(c.parent_comment_id) ?? []
      existing.push(c)
      replyMap.set(c.parent_comment_id, existing)
    } else {
      c.replies = []
      topLevel.push(c)
    }
  }

  for (const parent of topLevel) {
    parent.replies = replyMap.get(parent.id) ?? []
  }

  return topLevel
}


