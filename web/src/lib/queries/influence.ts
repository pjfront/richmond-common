import {
  supabase,
  RICHMOND_FIPS,
  isUuid,
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
import { getOfficials } from './council'

// ─── Influence Map: Item Center (S14-C) ─────────────────────

/**
 * Fetch the full influence map data bundle for a single agenda item.
 *
 * Consumed by <InfluenceMapItemSection> on the canonical agenda-item page
 * (`/meetings/[id]/items/[itemNumber]`). The legacy standalone route
 * `/influence/item/[id]` now permanently redirects to that canonical URL
 * (Phase 2.6).
 *
 * Strategy: Start from conflict_flags for this item (the scanner's output),
 * then enrich with contribution details, vote context, and fundraising totals
 * via separate focused queries. Each query is simple and composable.
 */
export async function getItemInfluenceMapData(
  agendaItemId: string,
  cityFips = RICHMOND_FIPS
): Promise<ItemInfluenceMapData | null> {
  if (!isUuid(agendaItemId)) return null

  // 1. Get the agenda item + meeting context
  const { data: item, error: itemError } = await supabase
    .from('agenda_items')
    .select(`
      id, title, item_number, description, plain_language_summary,
      summary_headline, category, financial_amount, is_consent_calendar,
      was_pulled_from_consent, resolution_number, meeting_id,
      meetings!inner(meeting_date, minutes_url)
    `)
    .is('agenda_source_retired_at', null)
    .eq('id', agendaItemId)
    .eq('meetings.city_fips', cityFips)
    .single()

  if (itemError || !item) {
    console.error('getItemInfluenceMapData: item query failed', { agendaItemId, itemError })
    return null
  }

  const meeting = item.meetings as unknown as {
    meeting_date: string
    minutes_url: string | null
  }

  // Flags and votes are independent once the agenda item is validated.
  const [{ data: flags }, votes] = await Promise.all([
    supabase
      .from('conflict_flags')
      .select('id, flag_type, description, evidence, confidence, official_id, match_details')
      .eq('agenda_item_id', agendaItemId)
      .eq('city_fips', cityFips)
      .eq('is_current', true)
      .gte('confidence', CONFIDENCE_PUBLISHED)
      .order('confidence', { ascending: false }),
    getItemVotes(agendaItemId, cityFips),
  ])

  const publishedFlags = (flags ?? []).filter(f => {
    if (f.flag_type !== 'donor_vendor_expenditure') return true
    const evidence = f.evidence as Record<string, unknown>[] | null
    const vendor = evidence?.[0]?.vendor
    if (typeof vendor === 'string' && isGovernmentEntity(vendor)) return false
    return true
  })

  // The three enrichment branches depend on flags but not on one another.
  const [contributions, behested_payments, related_items] = await Promise.all([
    buildContributionNarratives(agendaItemId, publishedFlags, votes, cityFips),
    getBehstedPaymentsForItem(agendaItemId, publishedFlags, cityFips),
    getRelatedAgendaItems(agendaItemId, publishedFlags, cityFips),
  ])

  return {
    item: {
      id: item.id as string,
      title: item.title as string,
      item_number: item.item_number as string,
      description: item.description as string | null,
      plain_language_summary: item.plain_language_summary as string | null,
      summary_headline: item.summary_headline as string | null,
      category: item.category as string | null,
      financial_amount: item.financial_amount as string | null,
      is_consent_calendar: item.is_consent_calendar as boolean,
      was_pulled_from_consent: item.was_pulled_from_consent as boolean,
      resolution_number: item.resolution_number as string | null,
      meeting_id: item.meeting_id as string,
      meeting_date: meeting.meeting_date,
    },
    votes,
    contributions,
    behested_payments,
    related_items,
    total_flags: publishedFlags.length,
    source_url: meeting.minutes_url,
    extracted_at: null,
  }
}

/** Get all votes on an agenda item with official context */
async function getItemVotes(
  agendaItemId: string,
  cityFips: string,
): Promise<ItemVoteContext[]> {
  const { data: motions } = await supabase
    .from('motions')
    .select(`
      id, result,
      votes(vote_choice, officials!inner(id, name))
    `)
    .eq('agenda_item_id', agendaItemId)
    .order('sequence_number', { ascending: false })
    .limit(1) // Take the final/decisive motion

  if (!motions || motions.length === 0) return []

  const motion = motions[0]
  const votes = motion.votes as unknown as Array<{
    vote_choice: string
    officials: { id: string; name: string }
  }>

  return votes.map(v => ({
    official_id: v.officials.id,
    official_name: v.officials.name,
    official_slug: nameToSlug(v.officials.name),
    vote_choice: v.vote_choice,
    motion_result: motion.result as string,
  }))
}

/**
 * Build enriched contribution narratives from conflict flags.
 *
 * For each flag with an official_id, query the contributions table
 * to get the actual financial records, then compute contextual data
 * (% of fundraising, same-way voters).
 */
async function buildContributionNarratives(
  agendaItemId: string,
  flags: Array<{ id: string; flag_type: string; description: string; evidence: unknown; confidence: number; official_id: string | null; match_details?: Record<string, unknown> | null }>,
  votes: ItemVoteContext[],
  cityFips: string,
): Promise<ContributionNarrativeData[]> {
  // Filter to contribution-related flags that have an official
  const contributionFlags = flags.filter(f =>
    f.official_id &&
    (f.flag_type === 'campaign_contribution' ||
     f.flag_type === 'vendor_donor_match' ||
     f.flag_type === 'donor_vendor_expenditure' ||
     f.flag_type === 'llc_ownership_chain')
  )

  if (contributionFlags.length === 0) return []

  // Get unique official IDs
  const officialIds = [...new Set(contributionFlags.map(f => f.official_id!).filter(Boolean))]

  // Batch: get official details + their committees
  const { data: officials } = await supabase
    .from('officials')
    .select('id, name')
    .in('id', officialIds)

  if (!officials || officials.length === 0) return []

  // Get committees for these officials
  const { data: committees } = await supabase
    .from('committees')
    .select('id, name, official_id')
    .in('official_id', officialIds)
    .eq('city_fips', cityFips)

  if (!committees || committees.length === 0) return []

  // Get all contributions to these committees
  const committeeIds = committees.map(c => c.id as string)
  const { data: allContribs, error: contribError } = await supabase
    .from('contributions')
    .select(`
      id, amount, contribution_date, source, filing_id,
      donor_id, committee_id,
      donors!inner(name, employer)
    `)
    .in('committee_id', committeeIds)
    .eq('city_fips', cityFips)
    .order('contribution_date', { ascending: false })
    .limit(5000) // Reasonable upper bound

  if (contribError) console.error('buildContributionNarratives: contributions query failed', contribError.message)
  if (!allContribs || allContribs.length === 0) return []

  // Build lookup: committee_id -> official_id
  const committeeToOfficial = new Map<string, string>()
  for (const c of committees) {
    if (c.official_id) committeeToOfficial.set(c.id as string, c.official_id as string)
  }

  // Build official lookup
  const officialMap = new Map<string, { name: string; slug: string }>()
  for (const o of officials) {
    officialMap.set(o.id as string, { name: o.name as string, slug: nameToSlug(o.name as string) })
  }

  // Compute per-official total fundraising
  const officialTotals = new Map<string, number>()
  for (const c of allContribs) {
    const officialId = committeeToOfficial.get(c.committee_id as string)
    if (officialId) {
      officialTotals.set(officialId, (officialTotals.get(officialId) ?? 0) + Number(c.amount))
    }
  }

  // Build vote lookup
  const voteByOfficial = new Map<string, string>()
  for (const v of votes) {
    voteByOfficial.set(v.official_id, v.vote_choice)
  }

  // Now build narratives: extract donor names from flag descriptions
  // and match against contribution records
  const narratives: ContributionNarrativeData[] = []

  for (const flag of contributionFlags) {
    const officialId = flag.official_id!
    const officialInfo = officialMap.get(officialId)
    if (!officialInfo) continue

    // Find committees belonging to this official
    const officialCommitteeIds = committees
      .filter(c => c.official_id === officialId)
      .map(c => c.id as string)

    // Get contributions to this official's committees
    const officialContribs = allContribs.filter(
      c => officialCommitteeIds.includes(c.committee_id as string)
    )

    // Group contributions by donor for this official
    type DonorGroup = {
      donor_name: string
      donor_employer: string | null
      contributions: typeof allContribs
      total: number
    }
    const donorGroups = new Map<string, DonorGroup>()
    // Also group by employer for vendor-to-employer matching
    const employerGroups = new Map<string, DonorGroup>()

    for (const contrib of officialContribs) {
      const donor = contrib.donors as unknown as { name: string; employer: string | null }
      const key = donor.name.toLowerCase()
      const group = donorGroups.get(key) ?? {
        donor_name: donor.name,
        donor_employer: donor.employer,
        contributions: [],
        total: 0,
      }
      group.contributions.push(contrib)
      group.total += Number(contrib.amount)
      donorGroups.set(key, group)

      // Build employer index — aggregates all employees at each employer
      if (donor.employer) {
        const empKey = donor.employer.toLowerCase()
        const empGroup = employerGroups.get(empKey) ?? {
          donor_name: donor.employer, // Use employer as display name
          donor_employer: donor.employer,
          contributions: [],
          total: 0,
        }
        empGroup.contributions.push(contrib)
        empGroup.total += Number(contrib.amount)
        employerGroups.set(empKey, empGroup)
      }
    }

    // Extract donor/entity name from match_details based on flag type
    const md = flag.match_details as Record<string, unknown> | null
    let matchedEntityName: string | undefined
    let matchByEmployer = false
    let vendorExpTotal: number | undefined
    let vendorExpCount: number | undefined
    let entityName: string | undefined
    let entityRelationship: string | undefined

    if (flag.flag_type === 'donor_vendor_expenditure') {
      // Vendor name is the entity — match against donor name or employer
      matchedEntityName = (md?.vendor as string | undefined)?.toLowerCase()
      const matchType = md?.donor_match_type as string | undefined
      matchByEmployer = matchType?.includes('employer') ?? false
      vendorExpTotal = md?.total_expenditure as number | undefined
      vendorExpCount = md?.expenditure_count as number | undefined
      entityName = md?.vendor as string | undefined
      entityRelationship = matchByEmployer ? 'employer' : 'direct'

      // Filter out government entity vendors — "city of richmond" as an employer
      // is civic noise, not a conflict signal (mirrors scanner-side filter)
      if (entityName && isGovernmentEntity(entityName)) continue
    } else if (flag.flag_type === 'llc_ownership_chain') {
      matchedEntityName = (md?.donor_name as string | undefined)?.toLowerCase()
      entityName = md?.org_name as string | undefined
      entityRelationship = md?.role as string | undefined ?? 'organization'
    } else {
      matchedEntityName = (md?.donor_name as string | undefined)?.toLowerCase()
    }

    // Find matching donor group using multi-strategy matching
    // For employer-matched vendor flags, search employer groups first (aggregated)
    const descLower = flag.description.toLowerCase()
    const searchGroups: Array<[string, DonorGroup]> = matchByEmployer
      ? [...employerGroups.entries()]
      : [...donorGroups.entries()]

    for (const [, group] of searchGroups) {
      const groupNameLower = group.donor_name.toLowerCase()

      let matched = false

      if (matchedEntityName && matchedEntityName.length > 3) {
        // Strategy 1: exact match
        if (groupNameLower === matchedEntityName) {
          matched = true
        }
        // Strategy 2: substring match
        else if (groupNameLower.includes(matchedEntityName) || matchedEntityName.includes(groupNameLower)) {
          matched = true
        }
      } else if (!matchedEntityName) {
        // Strategy 3: legacy description parsing (for flags without match_details)
        if (groupNameLower.length <= 3) continue
        if (!descLower.includes(groupNameLower)) continue
        matched = true
      }

      if (!matched) continue

      const officialTotal = officialTotals.get(officialId) ?? 0
      const voteChoice = voteByOfficial.get(officialId) ?? null

      // Count same-way voters and those without contributions from this donor
      const sameWayVoters = voteChoice
        ? votes.filter(v => v.vote_choice.toLowerCase() === voteChoice.toLowerCase() && v.official_id !== officialId)
        : []
      const sameWayWithoutContrib = sameWayVoters.filter(v => {
        // Check if this donor/employer contributed to this voter's committees
        const voterCommitteeIds = committees
          .filter(c => c.official_id === v.official_id)
          .map(c => c.id as string)
        return !allContribs.some(c => {
          if (!voterCommitteeIds.includes(c.committee_id as string)) return false
          const d = c.donors as unknown as { name: string; employer: string | null }
          if (matchByEmployer) {
            return (d.employer ?? '').toLowerCase() === groupNameLower
          }
          return d.name.toLowerCase() === groupNameLower
        })
      })

      const dates = group.contributions
        .map(c => c.contribution_date as string)
        .filter(Boolean)
        .sort()

      const contribRecords: ContributionRecord[] = group.contributions.map(c => {
        const donor = c.donors as unknown as { name: string; employer: string | null }
        const committeeId = c.committee_id as string
        const committee = committees.find(cm => cm.id === committeeId)
        return {
          contribution_id: c.id as string,
          donor_name: donor.name,
          donor_employer: donor.employer,
          committee_name: (committee?.name as string) ?? 'Unknown Committee',
          official_name: officialInfo.name,
          official_id: officialId,
          official_slug: officialInfo.slug,
          amount: Number(c.amount),
          contribution_date: c.contribution_date as string,
          source: c.source as string,
          filing_id: c.filing_id as string | null,
        }
      })

      narratives.push({
        official_id: officialId,
        official_name: officialInfo.name,
        official_slug: officialInfo.slug,
        donor_name: group.donor_name,
        donor_employer: group.donor_employer,
        total_contributed: group.total,
        contribution_count: group.contributions.length,
        earliest_date: dates[0] ?? '',
        latest_date: dates[dates.length - 1] ?? '',
        official_total_fundraising: officialTotal,
        percentage_of_fundraising: officialTotal > 0
          ? Math.round((group.total / officialTotal) * 1000) / 10
          : 0,
        vote_choice: voteChoice,
        same_way_voter_count: sameWayVoters.length,
        same_way_without_contribution: sameWayWithoutContrib.length,
        confidence: flag.confidence,
        source_tier: 'Tier 1',
        source_date: dates[dates.length - 1] ?? '',
        contributions: contribRecords,
        source_url: null,
        flag_type: flag.flag_type,
        flag_description: flag.description,
        vendor_expenditure_total: vendorExpTotal,
        vendor_expenditure_count: vendorExpCount,
        entity_name: entityName,
        entity_relationship: entityRelationship,
      })
    }
  }

  // Deduplicate: same official + donor pair (can appear from multiple flags)
  const seen = new Set<string>()
  return narratives.filter(n => {
    const key = `${n.official_id}:${n.donor_name.toLowerCase()}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

/** Get behested payments for entities appearing in this item's conflict flags */
async function getBehstedPaymentsForItem(
  agendaItemId: string,
  flags: Array<{ id: string; flag_type: string; description: string; evidence: unknown; confidence: number; official_id: string | null }>,
  cityFips: string,
): Promise<BehstedPaymentNarrativeData[]> {
  // Get official IDs from flags
  const officialIds = [...new Set(flags.map(f => f.official_id).filter(Boolean) as string[])]
  if (officialIds.length === 0) return []

  // Query behested payments for these officials
  const { data: payments } = await supabase
    .from('behested_payments')
    .select('*')
    .in('official_id', officialIds)
    .eq('city_fips', cityFips)
    .order('payment_date', { ascending: false })
    .limit(50)

  if (!payments || payments.length === 0) return []

  // Check if payors are also campaign contributors
  const payorNames = [...new Set(payments.map(p => (p.payor_name as string).toLowerCase()))]

  // Simple: check if any donor names match payor names
  const { data: matchingDonors } = await supabase
    .from('donors')
    .select('name')
    .eq('city_fips', cityFips)
    .limit(1000)

  const donorNames = new Set(
    (matchingDonors ?? []).map(d => (d.name as string).toLowerCase())
  )

  return payments.map(p => ({
    id: p.id as string,
    official_name: p.official_name as string,
    official_id: p.official_id as string | null,
    payor_name: p.payor_name as string,
    payee_name: p.payee_name as string,
    payee_description: p.payee_description as string | null,
    amount: p.amount ? Number(p.amount) : null,
    payment_date: p.payment_date as string | null,
    filing_date: p.filing_date as string | null,
    source_url: p.source_url as string | null,
    is_also_contributor: payorNames.some(
      pn => pn === (p.payor_name as string).toLowerCase() && donorNames.has(pn)
    ),
    contributor_total: null, // TODO: compute actual total if is_also_contributor
  }))
}

/**
 * Find related agenda items — other items flagged with the same officials.
 * Returns two groups: same-official items (direct relationship) and
 * same-meeting items (temporal context). Sorted by controversy.
 */
async function getRelatedAgendaItems(
  agendaItemId: string,
  flags: Array<{ id: string; flag_type: string; description: string; evidence: unknown; confidence: number; official_id: string | null }>,
  cityFips: string,
): Promise<RelatedAgendaItem[]> {
  const officialIds = [...new Set(flags.map(f => f.official_id).filter(Boolean) as string[])]
  if (officialIds.length === 0) return []

  // Find other flagged items for these officials, last 4 years only
  const fourYearsAgo = new Date()
  fourYearsAgo.setFullYear(fourYearsAgo.getFullYear() - 4)
  const cutoffDate = fourYearsAgo.toISOString().split('T')[0]

  const { data: relatedFlags } = await supabase
    .from('conflict_flags')
    .select(`
      agenda_item_id,
      agenda_items!inner(
        id, title, summary_headline, item_number, meeting_id, category,
        meetings!inner(meeting_date)
      )
    `)
    .in('official_id', officialIds)
    .eq('city_fips', cityFips)
    .eq('is_current', true)
    .gte('confidence', CONFIDENCE_PUBLISHED)
    .gte('agenda_items.meetings.meeting_date', cutoffDate)
    .neq('agenda_item_id', agendaItemId)
    .order('confidence', { ascending: false })
    .limit(200)

  if (!relatedFlags || relatedFlags.length === 0) return []

  // Deduplicate by agenda item ID and count flags per item
  const itemMap = new Map<string, {
    item: RelatedAgendaItem
    count: number
  }>()

  for (const rf of relatedFlags) {
    const ai = rf.agenda_items as unknown as {
      id: string
      title: string
      summary_headline: string | null
      item_number: string
      meeting_id: string
      category: string | null
      meetings: { meeting_date: string }
    }
    const itemId = ai.id
    const existing = itemMap.get(itemId)
    if (existing) {
      existing.count++
    } else {
      itemMap.set(itemId, {
        item: {
          id: itemId,
          title: ai.title,
          summary_headline: ai.summary_headline,
          item_number: ai.item_number,
          meeting_id: ai.meeting_id,
          meeting_date: ai.meetings.meeting_date,
          category: ai.category,
          flag_count: 1,
          has_split_vote: false,
        },
        count: 1,
      })
    }
  }

  // Check for split votes on all related items
  const relatedItemIds = [...itemMap.keys()]
  if (relatedItemIds.length > 0) {
    const BATCH = 100
    for (let i = 0; i < relatedItemIds.length; i += BATCH) {
      const batch = relatedItemIds.slice(i, i + BATCH)
      const { data: motions } = await supabase
        .from('motions')
        .select('agenda_item_id, votes(vote_choice)')
        .in('agenda_item_id', batch)

      if (motions) {
        for (const m of motions) {
          const votes = m.votes as unknown as Array<{ vote_choice: string }>
          const hasNay = votes.some(v => v.vote_choice.toLowerCase() === 'nay')
          if (hasNay) {
            const entry = itemMap.get(m.agenda_item_id as string)
            if (entry) entry.item.has_split_vote = true
          }
        }
      }
    }
  }

  // Sort by controversy: split votes first, then flag count, then date
  return Array.from(itemMap.values())
    .map(({ item, count }) => ({ ...item, flag_count: count }))
    .sort((a, b) => {
      // Split votes always rank higher
      if (a.has_split_vote !== b.has_split_vote) return a.has_split_vote ? -1 : 1
      // Then by flag count descending
      if (a.flag_count !== b.flag_count) return b.flag_count - a.flag_count
      // Then by date descending
      return b.meeting_date.localeCompare(a.meeting_date)
    })
    .slice(0, 15)
}

/** Get a single agenda item's basic info (for metadata generation + redirect lookups) */
export async function getAgendaItemBasic(
  agendaItemId: string,
  cityFips = RICHMOND_FIPS
) {
  const { data, error } = await supabase
    .from('agenda_items')
    .select('id, title, summary_headline, item_number, meeting_id, meetings!inner(meeting_date)')
    .is('agenda_source_retired_at', null)
    .eq('id', agendaItemId)
    .eq('meetings.city_fips', cityFips)
    .single()

  if (error || !data) return null
  const meeting = data.meetings as unknown as { meeting_date: string }
  return {
    id: data.id as string,
    title: data.title as string,
    summary_headline: data.summary_headline as string | null,
    item_number: data.item_number as string,
    meeting_id: data.meeting_id as string,
    meeting_date: meeting.meeting_date,
  }
}

