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

// ─── PAC Profiles (operator-only V1) ──────────────────────────────────

/** Slug a PAC committee. Stable across name variants when filer_id present. */
export function pacToSlug(name: string, filerId: string | null): string {
  const beforeComma = name.split(',')[0].trim()
  const base = beforeComma.length >= 6 ? beforeComma : name
  let slug = base
    .toLowerCase()
    .replace(/&/g, ' and ')
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9-]/g, '')
    .replace(/-+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60)
  if (filerId && filerId !== 'Pending' && /^\d+$/.test(filerId)) {
    slug = `${slug}-${filerId}`
  }
  return slug
}

/** Match the Python normalize_name pattern used in the donors table. */
function normalizeForDonorMatch(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim()
}

/** Pull a sponsor disclosure phrase from the committee name when present.
 *  Names like "X PAC, Sponsored by Y" → "Sponsored by Y".
 *  Chevron-funded ballot committees get the explicit Tier 3 disclosure. */
function inferSponsorDisclosure(name: string): string | null {
  const lower = name.toLowerCase()
  if (lower.includes('chevron')) return 'Funded by Chevron Richmond'
  const sponsorMatch = name.match(/sponsored by:?\s*([^,.]+)/i)
  if (sponsorMatch) {
    const sponsor = sponsorMatch[1].trim().replace(/\s+/g, ' ')
    if (sponsor.length < 200) return `Sponsored by ${sponsor}`
  }
  return null
}

/** List all PAC-shaped committees (no official_id) with at least one
 *  contribution, sorted by total raised. */
/** Heuristic name-pattern check for candidate-controlled committees.
 *  Used as a fallback for committees whose election_candidates link is
 *  broken (Gallon, Wassberg per the candidates_have_committee_linked
 *  liveness check) AND whose candidate_name field never got populated
 *  (which is the case for ALL fresh 2026 candidate committees). The
 *  underlying data hygiene problem is tracked elsewhere; this is the
 *  defensive layer that keeps candidate committees off /pac. */
/** Authoritative set of FPPC IDs registered with NetFile's Richmond CA
 *  agency (163). Source-of-truth file is `web/src/data/netfile-richmond-filers.json`,
 *  regenerated periodically from `mcp__netfile__get_committee_info(city='Richmond')`.
 *
 *  WHY THIS EXISTS: the committees table has a `city_fips = '0660620'`
 *  on every row, but that just means "ingested via the Richmond
 *  pipeline" — it doesn't verify the committee is actually registered
 *  with Richmond. Cross-jurisdictional committees (Richmond District
 *  Democratic Club is an SF club; Northern CA Carpenters file with
 *  state agencies; Tony Thurmond is state-level) auto-create in our
 *  table when they appear as donors on Richmond filings. The PAC
 *  index page's "Richmond political action committees" promise was
 *  silently false for ~12 of these entities until this filter landed.
 *
 *  GRADUATION PATH: this should become a `verified_local_filer`
 *  boolean column on the committees table populated by a sync job.
 *  Tracked elsewhere in the parking lot. */
const RICHMOND_NETFILE_FPPC_IDS = new Set<string>(RICHMOND_FILERS_DATA.fppc_ids as string[])

function isVerifiedRichmondFiler(filerId: string | null): boolean {
  // Null = no NetFile filer_id at all (paper filings, pre-NetFile data,
  // or sync race conditions). Allow through; the PAC won't appear with
  // misleading authority unless other filters miss it.
  if (filerId === null) return true
  // "Pending" = registered with Richmond NetFile, awaiting FPPC ID
  // assignment. Polluters Pay and Committee Against Measure P are in
  // this state. Allow.
  if (filerId === 'Pending') return true
  return RICHMOND_NETFILE_FPPC_IDS.has(filerId)
}

/** Lower-bound date for PAC contribution queries.
 *  All PAC profile/index views use a 5-cycle window
 *  (currentCycle-8 ... currentCycle, see getPACListWithCycleBars).
 *  Ten years is the smallest cap that covers that window with margin
 *  for off-cycle filings. Without it, every render pulled the full
 *  contributions table (22K+ rows growing) — a primary contributor
 *  to the 2026-05-06 Supabase I/O quota pause. Bumping the cap means
 *  bumping cycle_bars window in lockstep. */
function pacContributionLowerBound(): string {
  const d = new Date()
  d.setFullYear(d.getFullYear() - 10)
  return d.toISOString().slice(0, 10)
}

function looksLikeCandidateCommittee(name: string): boolean {
  // PACs and IE committees often contain "for [office]" because they
  // support candidates by name. These markers identify the supporting-
  // entity framing and override the "for [office]" pattern below:
  //   "Pride and Purpose Supporting Nat Bates [...] for City Council"
  //   "Richmond Progress, a Coalition of [...] Supporting Bates [...] for Mayor"
  //   "Richmond Votes Matters, Primarily Formed to Support Measure J"
  if (/\b(sponsored\s+by|supporting|coalition\s+(of|for|to)|primarily\s+formed)\b/i.test(name)) {
    return false
  }
  // "X for Mayor", "X for [Richmond] City Council", "X for District N",
  // "X for State Assembly", "X For Lieutenant Governor 2018", etc.
  if (/\bfor\s+(?:[\w'.]+\s+){0,3}(mayor|council|assembly|senate|congress|governor|attorney\s+general|controller|treasurer|board\s+of\s+supervisors|district\s+attorney|district\s+\d+|sheriff)\b/i.test(name)) {
    return true
  }
  // Action-verb prefixes: "Vote X", "Re-elect X", "Elect X",
  // "Committee to Elect X", "(The) Committee to Elect X", "Friends of X".
  // Two-word minimum after the verb prevents false positives like "Vote
  // for Change PAC" (hypothetical but cheap to defend against).
  if (/^(the\s+)?(vote|re-?elect|elect|committee\s+to\s+(re-?)?elect|friends\s+of)\s+\w+\s+\w/i.test(name)) {
    return true
  }
  return false
}

export async function getPACList(
  cityFips = RICHMOND_FIPS,
): Promise<PACAggregate[]> {
  // True PACs / IE / ballot-measure committees only. Defense in depth
  // because the underlying committees table is unreliable:
  //   1. official_id IS NULL (excludes sitting-official committees).
  //   2. candidate_name IS NULL (catches old 2018-2022 candidate
  //      committees where this field WAS populated).
  //   3. id NOT IN election_candidates.committee_id (authoritative
  //      link from candidates table — the strongest signal).
  //   4. Name doesn't match candidate-committee patterns (catches
  //      2026-cycle committees where the election_candidates link is
  //      broken or candidate_name regressed to NULL).
  //
  // The committee_type field is wildly unreliable: "Soheila Bana for
  // Council 2026" is filed as 'pac', "Polluters Pay" PAC is filed as
  // 'candidate'. So we don't trust it for filtering — only the four
  // checks above.
  const candidateCommitteeIds = new Set<string>()
  const { data: candRows } = await supabase
    .from('election_candidates')
    .select('committee_id')
    .eq('city_fips', cityFips)
    .not('committee_id', 'is', null)
  for (const r of candRows ?? []) {
    if (r.committee_id) candidateCommitteeIds.add(r.committee_id as string)
  }

  const { data: rawCommittees } = await supabase
    .from('committees')
    .select('id, name, filer_id, committee_type')
    .eq('city_fips', cityFips)
    .is('official_id', null)
    .is('candidate_name', null)
    .order('name')

  if (!rawCommittees || rawCommittees.length === 0) return []
  const committees = rawCommittees.filter((c) => {
    const id = c.id as string
    if (candidateCommitteeIds.has(id)) return false
    if (looksLikeCandidateCommittee(c.name as string)) return false
    if (!isVerifiedRichmondFiler((c.filer_id as string | null) ?? null)) return false
    return true
  })
  if (committees.length === 0) return []

  // Collapse rows that share a real FPPC filer_id. NetFile occasionally
  // creates multiple committee rows for the same filer when the
  // ballot-measure short name and the long "Primarily Formed to ..."
  // name surface in different filings. They split the same committee's
  // contributions across two ids; the user sees two rows with the same
  // truncated display name. The filer_id is the strongest dedup signal
  // — except for the literal "Pending" placeholder, which is shared by
  // genuinely-different unregistered committees and must NOT collapse.
  type CommitteeRow = (typeof committees)[number]
  const groups: Array<{ canonical: CommitteeRow; members: CommitteeRow[] }> = []
  const byFiler = new Map<string, CommitteeRow[]>()
  for (const c of committees) {
    const fid = (c.filer_id as string | null) ?? null
    if (fid && fid !== 'Pending') {
      const arr = byFiler.get(fid)
      if (arr) arr.push(c)
      else byFiler.set(fid, [c])
    } else {
      groups.push({ canonical: c, members: [c] })
    }
  }
  for (const [, members] of byFiler) {
    members.sort((a, b) => (b.name as string).length - (a.name as string).length)
    groups.push({ canonical: members[0], members })
  }
  const allMemberIds = groups.flatMap((g) => g.members.map((m) => m.id as string))

  // Bounded by date (last 10 years) because the PAC views only
  // present a 5-cycle window. High range cap remains as defense in
  // depth — PostgREST's default page size silently truncates large
  // result sets, and IAFF Local 188 alone has 8.4K contributions
  // even within window. Without the date filter every render
  // re-pulled the full contributions table (the 2026-05-06 I/O
  // quota pause).
  const { data: contribs } = await supabase
    .from('contributions')
    .select('committee_id, donor_id, amount, contribution_date')
    .in('committee_id', allMemberIds)
    .eq('city_fips', cityFips)
    .gte('contribution_date', pacContributionLowerBound())
    .range(0, 99999)

  // Stats are keyed by canonical id; contributions across all member
  // ids of a group fold into the canonical bucket.
  const memberToCanonical = new Map<string, string>()
  for (const g of groups) {
    const canonicalId = g.canonical.id as string
    for (const m of g.members) memberToCanonical.set(m.id as string, canonicalId)
  }
  const stats = new Map<
    string,
    { total: number; donors: Set<string>; rows: number; minDate: string | null; maxDate: string | null }
  >()
  for (const row of contribs ?? []) {
    const memberId = row.committee_id as string
    const canonicalId = memberToCanonical.get(memberId)
    if (!canonicalId) continue
    const amount = Number(row.amount ?? 0)
    const donorId = row.donor_id as string
    const date = row.contribution_date as string | null
    const existing = stats.get(canonicalId)
    if (existing) {
      existing.total += amount
      existing.donors.add(donorId)
      existing.rows += 1
      if (date && (!existing.minDate || date < existing.minDate)) existing.minDate = date
      if (date && (!existing.maxDate || date > existing.maxDate)) existing.maxDate = date
    } else {
      stats.set(canonicalId, {
        total: amount,
        donors: new Set([donorId]),
        rows: 1,
        minDate: date,
        maxDate: date,
      })
    }
  }

  const result: PACAggregate[] = []
  const seenSlugs = new Set<string>()
  for (const g of groups) {
    const canonical = g.canonical
    const id = canonical.id as string
    const s = stats.get(id)
    if (!s || s.total <= 0) continue
    const name = canonical.name as string
    const filerId = (canonical.filer_id as string | null) ?? null
    let slug = pacToSlug(name, filerId)
    if (seenSlugs.has(slug)) slug = `${slug}-${id.slice(0, 6)}`
    seenSlugs.add(slug)
    result.push({
      id,
      member_ids: g.members.map((m) => m.id as string),
      name,
      slug,
      filer_id: filerId,
      committee_type: (canonical.committee_type as string | null) ?? null,
      sponsor_disclosure: inferSponsorDisclosure(name),
      total_raised: s.total,
      donor_count: s.donors.size,
      contribution_count: s.rows,
      latest_contribution_date: s.maxDate,
      earliest_contribution_date: s.minDate,
    })
  }
  return result.sort((a, b) => b.total_raised - a.total_raised)
}

/** Resolve a PAC by slug. Walks getPACList() — fine for ~50 PACs. */
export async function getPACBySlug(
  slug: string,
  cityFips = RICHMOND_FIPS,
): Promise<PACAggregate | null> {
  const all = await getPACList(cityFips)
  return all.find((p) => p.slug === slug) ?? null
}

/** All contributions INTO this PAC, ordered most-recent first. Accepts
 *  either a single committee_id or the merged-set member_ids array
 *  produced by getPACList — necessary for filer_ids that surfaced
 *  under multiple committee rows in NetFile. */
export async function getPACContributions(
  committeeId: string | string[],
  cityFips = RICHMOND_FIPS,
): Promise<PACContributionRow[]> {
  const ids = Array.isArray(committeeId) ? committeeId : [committeeId]
  if (ids.length === 0) return []
  const { data } = await supabase
    .from('contributions')
    .select('amount, contribution_date, contribution_type, filing_id, donors!inner(name, employer)')
    .in('committee_id', ids)
    .eq('city_fips', cityFips)
    .gte('contribution_date', pacContributionLowerBound())
    .order('contribution_date', { ascending: false })
    .range(0, 19999)

  if (!data) return []
  return data.map((row) => {
    const donor = (row as Record<string, unknown>).donors as { name: string; employer: string | null }
    return {
      donor_name: donor.name,
      donor_employer: donor.employer,
      amount: Number(row.amount ?? 0),
      contribution_date: row.contribution_date as string,
      contribution_type: (row.contribution_type as string | null) ?? null,
      filing_id: (row.filing_id as string | null) ?? null,
    }
  })
}

/** Generate normalized-name variants for matching a PAC against donors.
 *  Captures the real-world pattern where a PAC like "Foo PAC, Sponsored
 *  by X" appears on another committee's filing as just "Foo PAC", or
 *  the variation pattern where the same entity registers as "EBWF" on
 *  one filing and "EBWF PAC" on another. Some PACs (notably IAFF Local
 *  188) have word-reordered donor names that need true entity
 *  resolution (S26) and are not caught by this. */
function donorNameVariantsFor(pacName: string): string[] {
  const variants = new Set<string>()
  variants.add(normalizeForDonorMatch(pacName))

  const beforeComma = pacName.split(',')[0].trim()
  if (beforeComma.length >= 4) {
    variants.add(normalizeForDonorMatch(beforeComma))

    // Drop trailing " PAC" if present
    if (/\s+pac$/i.test(beforeComma)) {
      const stripped = beforeComma.replace(/\s+pac$/i, '').trim()
      if (stripped.length >= 4) {
        variants.add(normalizeForDonorMatch(stripped))
      }
    }

    // Add " PAC" suffix if not present and base is reasonable length
    if (!/pac\b/i.test(beforeComma) && beforeComma.length >= 6) {
      variants.add(normalizeForDonorMatch(`${beforeComma} PAC`))
    }
  }

  return Array.from(variants).filter((v) => v.length >= 4)
}

/** Find places where this PAC's name appears as a donor on another
 *  committee's filing. Surfaces PAC -> candidate / PAC -> PAC transfers
 *  via the cross-filing 497 data we already capture. Matches against
 *  several normalized donor-name variants because real filings use
 *  short forms ("RPOA PAC") even when the PAC's registered name is
 *  long ("RPOA PAC, Sponsored by..."). Will pick up some name-collision
 *  noise that the operator vets before public graduation. */
export async function getPACOutgoing(
  pacName: string,
  cityFips = RICHMOND_FIPS,
): Promise<PACOutgoingRow[]> {
  const variants = donorNameVariantsFor(pacName)
  if (variants.length === 0) return []

  const { data: donorMatches } = await supabase
    .from('donors')
    .select('id')
    .eq('city_fips', cityFips)
    .in('normalized_name', variants)

  if (!donorMatches || donorMatches.length === 0) return []
  const donorIds = donorMatches.map((d) => d.id as string)

  const { data: contribs } = await supabase
    .from('contributions')
    .select('amount, contribution_date, contribution_type, filing_id, committee_id, committees!inner(id, name, candidate_name)')
    .in('donor_id', donorIds)
    .eq('city_fips', cityFips)
    .gte('contribution_date', pacContributionLowerBound())
    .order('contribution_date', { ascending: false })
    .range(0, 19999)

  if (!contribs) return []
  return contribs.map((row) => {
    const committee = (row as Record<string, unknown>).committees as {
      id: string
      name: string
      candidate_name: string | null
    }
    return {
      recipient_committee_name: committee.name,
      recipient_committee_id: committee.id,
      recipient_candidate_name: committee.candidate_name,
      amount: Number(row.amount ?? 0),
      contribution_date: row.contribution_date as string,
      contribution_type: (row.contribution_type as string | null) ?? null,
      filing_id: (row.filing_id as string | null) ?? null,
    }
  })
}

/** Independent expenditures filed BY this PAC: money it spent supporting
 *  or opposing a candidate without donating to that candidate's committee.
 *  Source: independent_expenditures table (CAL-ACCESS EXPN_CD, dedup'd in
 *  migration 102). Matched to the PAC by name variants since the source
 *  table has no committee_id foreign key — this is the same loose match
 *  pattern getPACOutgoing uses for cross-filing identification, with the
 *  same caveat that operator should vet for name-collision noise before
 *  public graduation. */
export async function getPACIndependentExpenditures(
  pacName: string,
  cityFips = RICHMOND_FIPS,
): Promise<PACIndependentExpenditureRow[]> {
  if (!pacName) return []
  // Exact case-insensitive match on the FULL filed name. An earlier
  // version added a fuzzy `beforeComma%` ILIKE pass to catch sponsorship-
  // suffix variants, but that conflated distinct PACs that share a
  // prefix — e.g. "East Bay Working Families, a coalition of unions
  // and community groups" (filer 1390351, $21.8M of IEs) vs "East Bay
  // Working Families, Issues, Sponsored by SEIU Local 1021" (filer
  // 1482538, $7.4K). Each PAC profile must show ONLY its own IEs, so
  // exact name matching is the safer default. We use ILIKE without
  // wildcards to be case-insensitive (the source has both mixed-case
  // and ALLCAPS variants of some committee names).
  const { data } = await supabase
    .from('independent_expenditures')
    .select(
      'candidate_name, support_or_oppose, amount, expenditure_date, payee_name, description, expenditure_code, filing_id',
    )
    .eq('city_fips', cityFips)
    .ilike('committee_name', pacName)
    .gte('expenditure_date', pacContributionLowerBound())
    .order('expenditure_date', { ascending: false })
    .range(0, 9999)

  return (data ?? []).map((row) => ({
    candidate_name: (row.candidate_name as string | null) ?? null,
    support_or_oppose: (row.support_or_oppose as 'S' | 'O' | null) ?? null,
    amount: Number(row.amount ?? 0),
    expenditure_date: row.expenditure_date as string,
    payee_name: (row.payee_name as string | null) ?? null,
    description: (row.description as string | null) ?? null,
    expenditure_code: (row.expenditure_code as string | null) ?? null,
    filing_id: (row.filing_id as string | null) ?? null,
  }))
}

/** Bulk version of getPACList + per-cycle aggregates. Powers the PAC
 *  index page V2 redesign where each row needs a sparkline of historical
 *  cycle activity. Avoids the N+1 pattern of calling getPACCycleBars
 *  for each PAC (39 round-trips becomes 3). */
export interface PACWithCycleBars extends PACAggregate {
  /** 5 most recent election cycles (2018, 2020, 2022, 2024, 2026 by
   *  default). Cycle bucketing rule: even years stay; odd years roll
   *  forward to the next even year. */
  cycle_bars: Array<{ cycle: number; in_total: number; out_total: number }>
  /** Raised in the current (most recent even-year) cycle. */
  current_cycle_in: number
  /** Outgoing flows in the current cycle (PAC's name as donor on
   *  another committee's filing in the current cycle). */
  current_cycle_out: number
}

export async function getPACListWithCycleBars(
  cityFips = RICHMOND_FIPS,
): Promise<PACWithCycleBars[]> {
  const pacs = await getPACList(cityFips)
  if (pacs.length === 0) return []

  // Bucketing: even year stays, odd year rolls forward to next even year.
  function cycleOf(dateStr: string | null): number | null {
    if (!dateStr) return null
    const year = parseInt(dateStr.slice(0, 4), 10)
    if (Number.isNaN(year)) return null
    return year % 2 === 0 ? year : year + 1
  }

  // Determine "current cycle" as the most recent even year not in the
  // future. Today is 2026, so current cycle = 2026.
  const currentYear = new Date().getFullYear()
  const currentCycle = currentYear % 2 === 0 ? currentYear : currentYear + 1

  // ── INCOMING: contributions where committee_id is any member of a PAC.
  // Some PACs collapse multiple committee rows that share an FPPC filer_id;
  // we must fetch contributions for every member_id and map each row
  // back to the canonical PAC id.
  const memberToPacId = new Map<string, string>()
  for (const p of pacs) {
    for (const m of p.member_ids) memberToPacId.set(m, p.id)
  }
  const allCommitteeIds = Array.from(memberToPacId.keys())
  const lowerBound = pacContributionLowerBound()
  const { data: inRows } = await supabase
    .from('contributions')
    .select('committee_id, amount, contribution_date')
    .in('committee_id', allCommitteeIds)
    .eq('city_fips', cityFips)
    .gte('contribution_date', lowerBound)
    .range(0, 99999)

  // ── OUTGOING: donors whose normalized_name matches a PAC's variants ─
  const variantToPacId = new Map<string, string>()
  for (const p of pacs) {
    for (const v of donorNameVariantsFor(p.name)) {
      if (!variantToPacId.has(v)) variantToPacId.set(v, p.id)
    }
  }
  const variants = Array.from(variantToPacId.keys())

  const donorIdToPacId = new Map<string, string>()
  if (variants.length > 0) {
    const { data: donorRows } = await supabase
      .from('donors')
      .select('id, normalized_name')
      .eq('city_fips', cityFips)
      .in('normalized_name', variants)
    for (const d of donorRows ?? []) {
      const pacId = variantToPacId.get(d.normalized_name as string)
      if (pacId) donorIdToPacId.set(d.id as string, pacId)
    }
  }

  const outRows: Array<{ pac_id: string; amount: number; date: string | null }> = []
  if (donorIdToPacId.size > 0) {
    const donorIds = Array.from(donorIdToPacId.keys())
    const { data: contribs } = await supabase
      .from('contributions')
      .select('donor_id, amount, contribution_date')
      .in('donor_id', donorIds)
      .eq('city_fips', cityFips)
      .gte('contribution_date', lowerBound)
      .range(0, 99999)
    for (const r of contribs ?? []) {
      const pacId = donorIdToPacId.get(r.donor_id as string)
      if (pacId) {
        outRows.push({
          pac_id: pacId,
          amount: Number(r.amount ?? 0),
          date: r.contribution_date as string | null,
        })
      }
    }
  }

  // ── Aggregate per-PAC, per-cycle ───────────────────────────────────
  const perPac = new Map<
    string,
    Map<number, { in_total: number; out_total: number }>
  >()
  for (const p of pacs) perPac.set(p.id, new Map())

  for (const r of inRows ?? []) {
    const memberId = r.committee_id as string
    const pacId = memberToPacId.get(memberId)
    if (!pacId) continue
    const cycle = cycleOf(r.contribution_date as string | null)
    if (cycle === null) continue
    const cycles = perPac.get(pacId)!
    const entry = cycles.get(cycle) ?? { in_total: 0, out_total: 0 }
    entry.in_total += Number(r.amount ?? 0)
    cycles.set(cycle, entry)
  }
  for (const r of outRows) {
    const cycle = cycleOf(r.date)
    if (cycle === null) continue
    const cycles = perPac.get(r.pac_id)!
    const entry = cycles.get(cycle) ?? { in_total: 0, out_total: 0 }
    entry.out_total += r.amount
    cycles.set(cycle, entry)
  }

  // ── Build result with last-5-cycles + current cycle totals ──────────
  // Use a 5-cycle window ending at currentCycle: e.g. 2018, 2020, 2022,
  // 2024, 2026. Show every cycle in the window even if zero, so all
  // sparklines have the same x-axis.
  const cycleWindow = [
    currentCycle - 8,
    currentCycle - 6,
    currentCycle - 4,
    currentCycle - 2,
    currentCycle,
  ]

  return pacs.map((p) => {
    const cycles = perPac.get(p.id)!
    const cycle_bars = cycleWindow.map((cycle) => {
      const entry = cycles.get(cycle) ?? { in_total: 0, out_total: 0 }
      return { cycle, in_total: entry.in_total, out_total: entry.out_total }
    })
    const current = cycles.get(currentCycle) ?? { in_total: 0, out_total: 0 }
    return {
      ...p,
      cycle_bars,
      current_cycle_in: current.in_total,
      current_cycle_out: current.out_total,
    }
  })
}

/** Per-cycle aggregates for the temporal layer of PAC profile pages.
 *  Returns one row per (cycle, direction) where:
 *    - cycle is the election-year integer (2018, 2020, 2022, 2024, 2026)
 *    - direction is 'in' (money raised by this PAC) or 'out' (money
 *      this PAC's name appeared as a donor on someone else's filing)
 *  Off-cycle years (odd years, plus the post-November stretch of even
 *  years) are bucketed into the NEXT election cycle since donors
 *  reasonably attribute Q3-2017 giving to the 2018 cycle. */
export async function getPACCycleBars(
  committeeId: string,
  pacName: string,
  cityFips = RICHMOND_FIPS,
): Promise<Array<{ cycle: number; in_total: number; out_total: number }>> {
  // Incoming: contributions table where committee_id matches
  const lowerBound = pacContributionLowerBound()
  const { data: inRows } = await supabase
    .from('contributions')
    .select('amount, contribution_date')
    .eq('committee_id', committeeId)
    .eq('city_fips', cityFips)
    .gte('contribution_date', lowerBound)

  // Outgoing: this PAC's name appearing as a donor on other filings
  const variants = donorNameVariantsFor(pacName)
  const outRows: Array<{ amount: number; contribution_date: string }> = []
  if (variants.length > 0) {
    const { data: donorMatches } = await supabase
      .from('donors')
      .select('id')
      .eq('city_fips', cityFips)
      .in('normalized_name', variants)
    const donorIds = (donorMatches ?? []).map((d) => d.id as string)
    if (donorIds.length > 0) {
      const { data } = await supabase
        .from('contributions')
        .select('amount, contribution_date')
        .in('donor_id', donorIds)
        .eq('city_fips', cityFips)
        .gte('contribution_date', lowerBound)
      for (const row of data ?? []) {
        outRows.push({
          amount: Number(row.amount ?? 0),
          contribution_date: row.contribution_date as string,
        })
      }
    }
  }

  // Bucket each contribution into an election cycle.
  // Even years (2018, 2020, ...) belong to that cycle.
  // Odd years (2017, 2019, ...) belong to the FOLLOWING even year's cycle.
  function cycleOf(dateStr: string | null): number | null {
    if (!dateStr) return null
    const year = parseInt(dateStr.slice(0, 4), 10)
    if (Number.isNaN(year)) return null
    return year % 2 === 0 ? year : year + 1
  }

  const buckets = new Map<number, { in_total: number; out_total: number }>()
  function bump(direction: 'in' | 'out', amount: number, date: string | null) {
    const cycle = cycleOf(date)
    if (cycle === null) return
    const entry = buckets.get(cycle) ?? { in_total: 0, out_total: 0 }
    if (direction === 'in') entry.in_total += amount
    else entry.out_total += amount
    buckets.set(cycle, entry)
  }
  for (const r of inRows ?? []) {
    bump('in', Number(r.amount ?? 0), r.contribution_date as string | null)
  }
  for (const r of outRows) {
    bump('out', r.amount, r.contribution_date)
  }

  return Array.from(buckets.entries())
    .map(([cycle, totals]) => ({ cycle, ...totals }))
    .sort((a, b) => a.cycle - b.cycle)
}

/** Donors x candidates conduit matrix for a single PAC profile.
 *
 *  This powers the Explore layer of PAC profile pages V2. Each cell
 *  represents the proportional dollar attribution from a donor (rows)
 *  through this PAC to a Richmond candidate (columns), computed
 *  per-cycle and summed.
 *
 *  Methodology, plain language:
 *    - For each election cycle the PAC has been active in, compute
 *      what share of the PAC's intake came from each donor.
 *    - For each candidate the PAC supported in that cycle, attribute
 *      that share of the PAC's outgoing flow to each donor.
 *    - Sum across all cycles to produce a per-(donor, candidate) cell.
 *
 *  This is necessarily approximate. PACs are pooled funds; we cannot
 *  attribute a specific incoming dollar to a specific outgoing dollar.
 *  But the per-cycle proportional model is the honest middle ground:
 *  it respects the temporal beat of campaign finance (money raised in
 *  2018 funds 2018-2020 outflows, not 2024 races) without overclaiming
 *  attribution that the underlying data can't support.
 *
 *  Returns null if the matrix would be uninteresting (fewer than 2
 *  donors with attributed flow, or fewer than 2 candidates with non-
 *  zero columns). The profile page falls back to the V1 detail tables
 *  in that case.
 */
export interface PACFlowMatrixDonor {
  name: string
  total_attributed: number
}

export interface PACFlowMatrixCandidate {
  name: string
  /** Slug for the candidate profile page, or null if no matching candidate
   *  row was found by name. Slug linking is best-effort in V1. */
  slug: string | null
  total_received_via_pac: number
}

export interface PACFlowMatrixCell {
  donor_name: string
  candidate_name: string
  amount: number
  /** Cycles in which this donor contributed AND this candidate received
   *  PAC flow. Useful for the temporal-mirror layer that follows. */
  cycles: number[]
}

export interface PACFlowMatrix {
  donors: PACFlowMatrixDonor[]
  candidates: PACFlowMatrixCandidate[]
  cells: PACFlowMatrixCell[]
  /** Total dollars represented across all cells. The sum of all cell
   *  amounts will be less than the PAC's total outflow if some outflows
   *  went to non-candidate committees (PAC-to-PAC transfers). */
  total_attributed: number
  /** Cycles spanned by the data, ascending. */
  cycles: number[]
}

export async function getPACFlowMatrix(
  committeeId: string | string[],
  pacName: string,
  cityFips = RICHMOND_FIPS,
  options: { maxDonors?: number; maxCandidates?: number } = {},
): Promise<PACFlowMatrix | null> {
  const maxDonors = options.maxDonors ?? 20
  const maxCandidates = options.maxCandidates ?? 12
  const ids = Array.isArray(committeeId) ? committeeId : [committeeId]
  if (ids.length === 0) return null

  function cycleOf(dateStr: string | null): number | null {
    if (!dateStr) return null
    const year = parseInt(dateStr.slice(0, 4), 10)
    if (Number.isNaN(year)) return null
    return year % 2 === 0 ? year : year + 1
  }

  // ── Incoming: who gave to this PAC, by cycle ─────────────────────────
  const lowerBound = pacContributionLowerBound()
  const { data: inRows } = await supabase
    .from('contributions')
    .select('amount, contribution_date, donors!inner(name)')
    .in('committee_id', ids)
    .eq('city_fips', cityFips)
    .gte('contribution_date', lowerBound)
    .range(0, 19999)

  if (!inRows || inRows.length === 0) return null

  type Inflow = { donor: string; cycle: number; amount: number }
  const inflows: Inflow[] = []
  for (const r of inRows) {
    const cycle = cycleOf(r.contribution_date as string | null)
    if (cycle === null) continue
    const donor = ((r as Record<string, unknown>).donors as { name: string }).name
    inflows.push({ donor, cycle, amount: Number(r.amount ?? 0) })
  }
  if (inflows.length === 0) return null

  // ── Outgoing: filings on other committees that name this PAC ─────────
  const variants = donorNameVariantsFor(pacName)
  if (variants.length === 0) return null

  const { data: donorMatches } = await supabase
    .from('donors')
    .select('id')
    .eq('city_fips', cityFips)
    .in('normalized_name', variants)

  const donorIds = (donorMatches ?? []).map((d) => d.id as string)
  if (donorIds.length === 0) return null

  const { data: outRows } = await supabase
    .from('contributions')
    .select('amount, contribution_date, committees!inner(candidate_name)')
    .in('donor_id', donorIds)
    .eq('city_fips', cityFips)
    .gte('contribution_date', lowerBound)
    .range(0, 19999)

  type Outflow = { candidate: string; cycle: number; amount: number }
  const outflows: Outflow[] = []
  for (const r of outRows ?? []) {
    const cycle = cycleOf(r.contribution_date as string | null)
    if (cycle === null) continue
    const committee = (r as Record<string, unknown>).committees as {
      candidate_name: string | null
    }
    if (!committee.candidate_name) continue
    outflows.push({
      candidate: committee.candidate_name,
      cycle,
      amount: Number(r.amount ?? 0),
    })
  }
  if (outflows.length === 0) return null

  // ── Per-cycle aggregates ─────────────────────────────────────────────
  const intakeByCycle = new Map<number, number>()
  for (const f of inflows) {
    intakeByCycle.set(f.cycle, (intakeByCycle.get(f.cycle) ?? 0) + f.amount)
  }

  const donorByCycle = new Map<number, Map<string, number>>()
  for (const f of inflows) {
    let donorMap = donorByCycle.get(f.cycle)
    if (!donorMap) {
      donorMap = new Map()
      donorByCycle.set(f.cycle, donorMap)
    }
    donorMap.set(f.donor, (donorMap.get(f.donor) ?? 0) + f.amount)
  }

  const outflowByCycle = new Map<number, Map<string, number>>()
  for (const o of outflows) {
    let candMap = outflowByCycle.get(o.cycle)
    if (!candMap) {
      candMap = new Map()
      outflowByCycle.set(o.cycle, candMap)
    }
    candMap.set(o.candidate, (candMap.get(o.candidate) ?? 0) + o.amount)
  }

  // ── Build cells via proportional attribution per cycle ───────────────
  // Nested map: donor -> candidate -> { amount, cycles }. A nested
  // structure avoids encoding donor/candidate names into a single key,
  // since both can contain arbitrary punctuation that would be lossy.
  const cellAccumulator = new Map<
    string,
    Map<string, { amount: number; cycles: Set<number> }>
  >()

  const overlapCycles = new Set<number>()
  for (const cycle of intakeByCycle.keys()) {
    if (outflowByCycle.has(cycle)) overlapCycles.add(cycle)
  }

  for (const cycle of overlapCycles) {
    const intake = intakeByCycle.get(cycle) ?? 0
    if (intake <= 0) continue
    const donors = donorByCycle.get(cycle)!
    const candidates = outflowByCycle.get(cycle)!
    for (const [donor, donorAmount] of donors) {
      const share = donorAmount / intake
      let perDonor = cellAccumulator.get(donor)
      if (!perDonor) {
        perDonor = new Map()
        cellAccumulator.set(donor, perDonor)
      }
      for (const [candidate, candAmount] of candidates) {
        const attributed = share * candAmount
        if (attributed <= 0) continue
        const entry = perDonor.get(candidate) ?? { amount: 0, cycles: new Set<number>() }
        entry.amount += attributed
        entry.cycles.add(cycle)
        perDonor.set(candidate, entry)
      }
    }
  }

  if (cellAccumulator.size === 0) return null

  // ── Pick top donors and top candidates ───────────────────────────────
  const donorTotals = new Map<string, number>()
  const candidateTotals = new Map<string, number>()
  for (const [donor, perDonor] of cellAccumulator) {
    for (const [candidate, entry] of perDonor) {
      donorTotals.set(donor, (donorTotals.get(donor) ?? 0) + entry.amount)
      candidateTotals.set(
        candidate,
        (candidateTotals.get(candidate) ?? 0) + entry.amount,
      )
    }
  }

  const topDonors = Array.from(donorTotals.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, maxDonors)
    .map(([name, total_attributed]) => ({ name, total_attributed }))

  const topCandidates = Array.from(candidateTotals.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, maxCandidates)
    .map(([name, total_received_via_pac]) => ({
      name,
      total_received_via_pac,
      slug: null as string | null,
    }))

  if (topDonors.length < 2 || topCandidates.length < 2) return null

  // Slug linking to candidate profile pages is deferred to V2. The
  // route is /elections/[election]/candidates/[name], which requires
  // both the election slug and the candidate name slug; the matrix
  // does not have election context. For V1 candidates render as plain
  // text and the user navigates via the existing candidate index.

  // ── Filter cells to top-N x top-N intersection ───────────────────────
  const donorSet = new Set(topDonors.map((d) => d.name))
  const candSet = new Set(topCandidates.map((c) => c.name))
  const cells: PACFlowMatrixCell[] = []
  let totalAttributed = 0
  for (const [donor, perDonor] of cellAccumulator) {
    if (!donorSet.has(donor)) continue
    for (const [candidate, entry] of perDonor) {
      if (!candSet.has(candidate)) continue
      cells.push({
        donor_name: donor,
        candidate_name: candidate,
        amount: entry.amount,
        cycles: Array.from(entry.cycles).sort(),
      })
      totalAttributed += entry.amount
    }
  }

  return {
    donors: topDonors,
    candidates: topCandidates,
    cells,
    total_attributed: totalAttributed,
    cycles: Array.from(overlapCycles).sort(),
  }
}

