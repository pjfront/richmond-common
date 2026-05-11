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

// ─── Topic Browsing (S23.3) ─────────────────────────────────

export interface TopicCount {
  topic_label: string
  item_count: number
  latest_meeting_date: string
}

/** Get all topic labels with item counts and most recent meeting date. */
export async function getTopicCounts(cityFips = RICHMOND_FIPS): Promise<TopicCount[]> {
  const { data, error } = await supabase
    .from('agenda_items')
    .select('topic_label, meeting_id, meetings!inner(meeting_date, city_fips)')
    .eq('meetings.city_fips', cityFips)
    .not('topic_label', 'is', null)

  if (error) {
    console.error('getTopicCounts query failed:', error)
    return []
  }

  // Aggregate in JS since Supabase doesn't support GROUP BY directly
  const counts = new Map<string, { count: number; latest: string }>()
  for (const row of (data ?? []) as Array<Record<string, unknown>>) {
    const label = row.topic_label as string
    const meeting = row.meetings as unknown as { meeting_date: string }
    const existing = counts.get(label)
    if (!existing) {
      counts.set(label, { count: 1, latest: meeting.meeting_date })
    } else {
      existing.count++
      if (meeting.meeting_date > existing.latest) {
        existing.latest = meeting.meeting_date
      }
    }
  }

  return Array.from(counts.entries())
    .map(([label, { count, latest }]) => ({
      topic_label: label,
      item_count: count,
      latest_meeting_date: latest,
    }))
    .sort((a, b) => b.item_count - a.item_count)
}

export interface TopicItem {
  id: string
  meeting_id: string
  meeting_date: string
  meeting_type: string
  item_number: string
  title: string
  summary_headline: string | null
  category: string | null
  financial_amount: string | null
  public_comment_count: number
}

const COLS_TOPIC_ITEM = 'id, meeting_id, item_number, title, summary_headline, category, financial_amount, public_comment_count, meetings!inner(meeting_date, meeting_type, city_fips)'

/** Get agenda items for a specific topic label, newest first. */
export async function getTopicItems(
  topicLabel: string,
  limit = 50,
  cityFips = RICHMOND_FIPS,
): Promise<TopicItem[]> {
  const { data, error } = await supabase
    .from('agenda_items')
    .select(COLS_TOPIC_ITEM)
    .eq('topic_label', topicLabel)
    .eq('meetings.city_fips', cityFips)
    .order('meetings(meeting_date)', { ascending: false })
    .limit(limit)

  if (error) {
    console.error('getTopicItems query failed:', error)
    return []
  }

  return ((data ?? []) as Array<Record<string, unknown>>).map((row) => {
    const meeting = row.meetings as unknown as { meeting_date: string; meeting_type: string }
    return {
      id: row.id as string,
      meeting_id: row.meeting_id as string,
      meeting_date: meeting.meeting_date,
      meeting_type: meeting.meeting_type,
      item_number: row.item_number as string,
      title: row.title as string,
      summary_headline: row.summary_headline as string | null,
      category: row.category as string | null,
      financial_amount: row.financial_amount as string | null,
      public_comment_count: Number(row.public_comment_count),
    }
  })
}


// ─── Promoted topics (organic recurrence-based taxonomy) ────
// A topic_label only earns a navigation surface (sidebar chip,
// /topics card) once it has BOTH crossed an item-count bar AND
// appeared in multiple distinct meetings. The two-axis test rules
// out single-meeting clusters (6 closed-session items tagged the
// same way doesn't prove cross-meeting interest) while still
// promoting issues that genuinely recur. Both knobs are editorial.

export const TOPIC_PROMOTION_MIN_ITEMS = 5
export const TOPIC_PROMOTION_MIN_MEETINGS = 3

/** Back-compat alias used in user-facing copy on /topics. */
export const TOPIC_PROMOTION_THRESHOLD = TOPIC_PROMOTION_MIN_ITEMS

export interface PromotedTopic {
  label: string
  slug: string
  item_count: number
  meeting_count: number
  latest_meeting_date: string
}

/** Convert a topic_label into a URL-safe slug. */
export function topicLabelToSlug(label: string): string {
  return label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

/** Topics passing both item and meeting recurrence thresholds, sorted by recency. */
export async function getPromotedTopics(
  minItems = TOPIC_PROMOTION_MIN_ITEMS,
  minMeetings = TOPIC_PROMOTION_MIN_MEETINGS,
  cityFips = RICHMOND_FIPS,
): Promise<PromotedTopic[]> {
  const { data, error } = await supabase
    .from('agenda_items')
    .select('topic_label, meeting_id, meetings!inner(meeting_date, city_fips)')
    .eq('meetings.city_fips', cityFips)
    .not('topic_label', 'is', null)

  if (error) {
    console.error('getPromotedTopics query failed:', error)
    return []
  }

  const acc = new Map<string, { items: number; meetingIds: Set<string>; latest: string }>()
  for (const row of (data ?? []) as Array<Record<string, unknown>>) {
    const label = row.topic_label as string
    const meetingId = row.meeting_id as string
    const meeting = row.meetings as unknown as { meeting_date: string }
    const existing = acc.get(label)
    if (!existing) {
      acc.set(label, { items: 1, meetingIds: new Set([meetingId]), latest: meeting.meeting_date })
    } else {
      existing.items++
      existing.meetingIds.add(meetingId)
      if (meeting.meeting_date > existing.latest) existing.latest = meeting.meeting_date
    }
  }

  return Array.from(acc.entries())
    .filter(([, v]) => v.items >= minItems && v.meetingIds.size >= minMeetings)
    .map(([label, v]) => ({
      label,
      slug: topicLabelToSlug(label),
      item_count: v.items,
      meeting_count: v.meetingIds.size,
      latest_meeting_date: v.latest,
    }))
    .sort((a, b) => b.latest_meeting_date.localeCompare(a.latest_meeting_date))
}

/** JSON-serializable label list for passing across server→client boundaries. */
export async function getPromotedTopicLabels(
  minItems = TOPIC_PROMOTION_MIN_ITEMS,
  minMeetings = TOPIC_PROMOTION_MIN_MEETINGS,
  cityFips = RICHMOND_FIPS,
): Promise<string[]> {
  const topics = await getPromotedTopics(minItems, minMeetings, cityFips)
  return topics.map((t) => t.label)
}

