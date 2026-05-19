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

// ─── Financial Connections (S10.4) ───────────────────────────

export async function getFinancialConnectionsForOfficial(
  officialId: string,
  cityFips = RICHMOND_FIPS
): Promise<FinancialConnectionFlag[]> {
  // Query 1: Get all published conflict flags for this official
  const { data: rawFlags, error: flagError } = await supabase
    .from('conflict_flags')
    .select(`
      id, flag_type, confidence, description, evidence,
      meeting_id, agenda_item_id,
      meetings!inner(meeting_date),
      agenda_items!inner(title, item_number, category)
    `)
    .eq('official_id', officialId)
    .eq('city_fips', cityFips)
    .eq('is_current', true)
    .gte('confidence', CONFIDENCE_PUBLISHED)
    .order('confidence', { ascending: false })
    .limit(500)

  if (flagError) throw flagError
  if (!rawFlags || rawFlags.length === 0) return []

  // Query 2: Get votes for this official on the flagged agenda items
  // Join path: agenda_item_id → motions → votes
  const agendaItemIds = [...new Set(rawFlags.map((f) => f.agenda_item_id).filter(Boolean))]

  // Batch the .in() query to avoid Supabase URL length limits
  const BATCH_SIZE = 200
  type MotionVoteRow = { agenda_item_id: string; sequence_number: number; result: string; vote_tally: string | null; votes: Array<{ vote_choice: string }> }
  const allMotionVotes: MotionVoteRow[] = []
  for (let i = 0; i < agendaItemIds.length; i += BATCH_SIZE) {
    const batch = agendaItemIds.slice(i, i + BATCH_SIZE)
    const { data: motionVotesBatch, error: voteError } = await supabase
      .from('motions')
      .select('agenda_item_id, sequence_number, result, vote_tally, votes!inner(vote_choice)')
      .in('agenda_item_id', batch)
      .eq('votes.official_id', officialId)
      .order('sequence_number', { ascending: false })
    if (voteError) throw voteError
    if (motionVotesBatch) allMotionVotes.push(...(motionVotesBatch as unknown as MotionVoteRow[]))
  }
  const motionVotes = allMotionVotes

  // Build vote lookup: for each agenda item, take the highest sequence_number motion's vote
  const voteByAgendaItem = new Map<string, { vote_choice: string; motion_result: string; is_unanimous: boolean | null }>()
  for (const m of motionVotes ?? []) {
    const itemId = m.agenda_item_id
    if (!voteByAgendaItem.has(itemId)) {
      const votes = m.votes as unknown as Array<{ vote_choice: string }>
      if (votes.length > 0) {
        const nays = votes.filter(v => v.vote_choice === 'nay').length
        const ayes = votes.filter(v => v.vote_choice === 'aye').length
        voteByAgendaItem.set(itemId, {
          vote_choice: votes[0].vote_choice,
          motion_result: m.result,
          is_unanimous: nays === 0 || ayes === 0,
        })
      }
    }
  }

  // Merge flags with vote data
  return rawFlags.map((f) => {
    const meeting = f.meetings as unknown as { meeting_date: string }
    const item = f.agenda_items as unknown as { title: string; item_number: string; category: string | null }
    const vote = voteByAgendaItem.get(f.agenda_item_id)

    return {
      id: f.id,
      flag_type: f.flag_type,
      confidence: f.confidence,
      description: f.description,
      evidence: f.evidence as Record<string, unknown>[],
      meeting_id: f.meeting_id,
      meeting_date: meeting.meeting_date,
      agenda_item_id: f.agenda_item_id,
      agenda_item_title: item.title,
      agenda_item_number: item.item_number,
      agenda_item_category: item.category,
      vote_choice: (vote?.vote_choice as FinancialConnectionFlag['vote_choice']) ?? null,
      motion_result: vote?.motion_result ?? null,
      is_unanimous: vote?.is_unanimous ?? null,
    }
  })
}

export function buildOfficialConnectionSummary(
  officialId: string,
  officialName: string,
  flags: FinancialConnectionFlag[]
): OfficialConnectionSummary {
  const flagTypeBreakdown: Record<string, number> = {}
  let votedInFavor = 0
  let votedAgainst = 0
  let abstained = 0
  let absentFor = 0
  let noVoteRecorded = 0

  for (const flag of flags) {
    flagTypeBreakdown[flag.flag_type] = (flagTypeBreakdown[flag.flag_type] ?? 0) + 1

    // Only count voted_in_favor / voted_against for non-unanimous (contested) votes.
    // Unanimous votes are noise — every member voted the same way.
    const isContested = flag.is_unanimous === false
    switch (flag.vote_choice) {
      case 'aye': if (isContested) votedInFavor++; break
      case 'nay': if (isContested) votedAgainst++; break
      case 'abstain': abstained++; break
      case 'absent': absentFor++; break
      default: noVoteRecorded++; break
    }
  }

  return {
    official_id: officialId,
    official_name: officialName,
    official_slug: nameToSlug(officialName),
    total_flags: flags.length,
    voted_in_favor: votedInFavor,
    voted_against: votedAgainst,
    abstained,
    absent_for: absentFor,
    no_vote_recorded: noVoteRecorded,
    flag_type_breakdown: flagTypeBreakdown,
    flags,
  }
}

export async function getAllFinancialConnectionSummaries(
  cityFips = RICHMOND_FIPS
): Promise<OfficialConnectionSummary[]> {
  // Fetch all published flags across all officials
  const { data: rawFlags, error: flagError } = await supabase
    .from('conflict_flags')
    .select(`
      id, flag_type, confidence, description, evidence,
      meeting_id, agenda_item_id, official_id,
      meetings!inner(meeting_date),
      agenda_items!inner(title, item_number, category),
      officials!inner(name)
    `)
    .eq('city_fips', cityFips)
    .eq('is_current', true)
    .gte('confidence', CONFIDENCE_PUBLISHED)
    .order('confidence', { ascending: false })
    .limit(1000)

  if (flagError) {
    console.error('getAllFinancialConnectionSummaries query failed:', flagError)
    return []
  }
  if (!rawFlags || rawFlags.length === 0) return []

  // Batch-fetch votes for all flagged agenda items across all officials
  const agendaItemIds = [...new Set(rawFlags.map((f) => f.agenda_item_id).filter(Boolean))]
  const officialIds = [...new Set(rawFlags.map((f) => f.official_id).filter(Boolean))]

  // Batch the .in() query to avoid Supabase URL length limits
  type AllMotionVoteRow = { agenda_item_id: string; sequence_number: number; result: string; vote_tally: string | null; votes: Array<{ official_id: string; vote_choice: string }> }
  const allMotionVotes: AllMotionVoteRow[] = []
  for (let i = 0; i < agendaItemIds.length; i += 200) {
    const batch = agendaItemIds.slice(i, i + 200)
    const { data: motionVotesBatch, error: voteError } = await supabase
      .from('motions')
      .select('agenda_item_id, sequence_number, result, vote_tally, votes!inner(official_id, vote_choice)')
      .in('agenda_item_id', batch)
      .in('votes.official_id', officialIds)
      .order('sequence_number', { ascending: false })
    if (voteError) {
      console.error('getAllFinancialConnectionSummaries vote query failed:', voteError)
      break
    }
    if (motionVotesBatch) allMotionVotes.push(...(motionVotesBatch as unknown as AllMotionVoteRow[]))
  }
  const motionVotes = allMotionVotes

  // Build vote lookup: (agenda_item_id, official_id) → vote
  // Also track unanimity per agenda item (shared across officials)
  const voteKey = (itemId: string, officialId: string) => `${itemId}::${officialId}`
  const voteMap = new Map<string, { vote_choice: string; motion_result: string; is_unanimous: boolean | null }>()
  const unanimityByItem = new Map<string, boolean | null>()
  for (const m of motionVotes ?? []) {
    // Compute unanimity once per agenda item (from the highest-sequence motion)
    if (!unanimityByItem.has(m.agenda_item_id)) {
      const voteRecords = m.votes as unknown as Array<{ official_id: string; vote_choice: string }>
      if (voteRecords.length > 0) {
        const nays = voteRecords.filter(v => v.vote_choice === 'nay').length
        const ayes = voteRecords.filter(v => v.vote_choice === 'aye').length
        unanimityByItem.set(m.agenda_item_id, nays === 0 || ayes === 0)
      } else {
        unanimityByItem.set(m.agenda_item_id, null)
      }
    }
    const is_unanimous = unanimityByItem.get(m.agenda_item_id) ?? null
    const votes = m.votes as unknown as Array<{ official_id: string; vote_choice: string }>
    for (const v of votes) {
      const key = voteKey(m.agenda_item_id, v.official_id)
      if (!voteMap.has(key)) {
        voteMap.set(key, { vote_choice: v.vote_choice, motion_result: m.result, is_unanimous })
      }
    }
  }

  // Group flags by official
  const officialFlagsMap = new Map<string, { name: string; flags: FinancialConnectionFlag[] }>()
  for (const f of rawFlags) {
    if (!f.official_id) continue
    const meeting = f.meetings as unknown as { meeting_date: string }
    const item = f.agenda_items as unknown as { title: string; item_number: string; category: string | null }
    const official = f.officials as unknown as { name: string }
    const vote = voteMap.get(voteKey(f.agenda_item_id, f.official_id))

    if (!officialFlagsMap.has(f.official_id)) {
      officialFlagsMap.set(f.official_id, { name: official.name, flags: [] })
    }

    officialFlagsMap.get(f.official_id)!.flags.push({
      id: f.id,
      flag_type: f.flag_type,
      confidence: f.confidence,
      description: f.description,
      evidence: f.evidence as Record<string, unknown>[],
      meeting_id: f.meeting_id,
      meeting_date: meeting.meeting_date,
      agenda_item_id: f.agenda_item_id,
      agenda_item_title: item.title,
      agenda_item_number: item.item_number,
      agenda_item_category: item.category,
      vote_choice: (vote?.vote_choice as FinancialConnectionFlag['vote_choice']) ?? null,
      motion_result: vote?.motion_result ?? null,
      is_unanimous: vote?.is_unanimous ?? null,
    })
  }

  // Build summaries sorted by flag count descending
  return Array.from(officialFlagsMap.entries())
    .map(([id, { name, flags }]) => buildOfficialConnectionSummary(id, name, flags))
    .sort((a, b) => b.total_flags - a.total_flags)
}


// ─── Candidate Full Donor List (cycle-partitioned) ────────────────────────

export async function getFullCandidateDonors(
  committeeId: string,
  electionDate: string,
  cityFips = RICHMOND_FIPS,
  limit = 100,
): Promise<CandidateDonorsByCycle> {
  const electionYear = new Date(electionDate + 'T00:00:00').getFullYear()
  const cycleStart = `${electionYear - 1}-01-01`
  // Some committees span multiple election cycles (Willis 2020 +
  // 2024 reelection sit on one continuous committee). Without an
  // upper bound on the "this cycle" window, the older candidacy's
  // page conflates donors across both cycles. End the window 60 days
  // after election day to absorb late filings + recounts.
  const cycleEnd = new Date(electionDate + 'T00:00:00')
  cycleEnd.setDate(cycleEnd.getDate() + 60)
  const cycleEndIso = cycleEnd.toISOString().slice(0, 10)

  const cycleLabel = `Jan ${electionYear - 1} – ${new Date(electionDate + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', year: 'numeric' })}`

  const { data: contribs } = await supabase
    .from('contributions')
    .select('amount, contribution_date, donors!inner(name, employer)')
    .eq('committee_id', committeeId)
    .eq('city_fips', cityFips)

  if (!contribs || contribs.length === 0) {
    return { cycleDonors: [], priorDonors: [], cycleLabel }
  }

  const govEntityPattern = /^(the )?(city|county|state|town) of\b/

  function aggregateDonors(rows: NonNullable<typeof contribs>): CandidateTopDonor[] {
    const map = new Map<string, { employer: string | null; total: number; count: number }>()
    for (const row of rows) {
      const donor = (row as Record<string, unknown>).donors as { name: string; employer: string | null }
      if (govEntityPattern.test(donor.name.toLowerCase())) continue
      const existing = map.get(donor.name)
      if (existing) {
        existing.total += row.amount as number
        existing.count += 1
      } else {
        map.set(donor.name, { employer: donor.employer, total: row.amount as number, count: 1 })
      }
    }
    return Array.from(map.entries())
      .map(([name, d]) => ({ donor_name: name, employer: d.employer, total_contributed: d.total, contribution_count: d.count }))
      .sort((a, b) => b.total_contributed - a.total_contributed)
      .slice(0, limit)
  }

  const cycleContribs = contribs.filter(c => {
    const d = c.contribution_date as string | null
    return d != null && d >= cycleStart && d <= cycleEndIso
  })
  const priorContribs = contribs.filter(c => {
    const d = c.contribution_date as string | null
    // Anything strictly before this cycle's window. Contributions
    // *after* the cycle's end belong to a later candidacy on the
    // same committee — they don't appear on this older page.
    return d != null && d < cycleStart
  })

  return {
    cycleDonors: aggregateDonors(cycleContribs),
    priorDonors: aggregateDonors(priorContribs),
    cycleLabel,
  }
}

