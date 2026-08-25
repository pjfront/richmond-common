/**
 * Organization profile queries (S28.3).
 *
 * Reads from donors table (entity_type = 'union' | 'corporation', grouped by
 * entity_slug) and contributions table.  One org may have multiple donor rows
 * (name variants that share the same entity_slug); queries aggregate across
 * all of them.
 *
 * Pattern: reuse the PAC query shape (aggregate → detail → cycle bars) but
 * simplified — orgs are donors, so we only track money OUT (org → committees),
 * not money IN.
 */

import { supabase, RICHMOND_FIPS } from './_shared'
import type {
  OrgAggregate,
  OrgOutgoingRow,
  PACIndependentExpenditureRow,
} from '../types'

// ─── Helpers ───────────────────────────────────────────────────────────

const ORG_ENTITY_TYPES = ['union', 'corporation'] as const

/** Current election cycle (e.g. 2026). Odd years roll forward. */
function currentElectionCycle(): number {
  const y = new Date().getFullYear()
  return y % 2 === 0 ? y : y + 1
}

/** Pull a mandatory disclosure for per-source-tier rules.
 *  Chevron → "Funded by Chevron Richmond" per richmond.md Tier 3 rule. */
function inferOrgDisclosure(name: string): string | null {
  if (name.toLowerCase().includes('chevron')) return 'Funded by Chevron Richmond'
  return null
}

/** Bucket a date into its election cycle (even year stays, odd year rolls forward). */
function cycleOf(dateStr: string | null): number | null {
  if (!dateStr) return null
  const year = parseInt(dateStr.slice(0, 4), 10)
  if (Number.isNaN(year)) return null
  return year % 2 === 0 ? year : year + 1
}

// ─── Index ─────────────────────────────────────────────────────────────

export async function getOrgList(
  cityFips = RICHMOND_FIPS,
): Promise<OrgAggregate[]> {
  // Get all org-typed donors with an entity_slug.
  const { data: donors } = await supabase
    .from('donors')
    .select('id, name, entity_type, entity_slug, total_contributed, distinct_recipients, contribution_span_days')
    .eq('city_fips', cityFips)
    .in('entity_type', ORG_ENTITY_TYPES)
    .not('entity_slug', 'is', null)
    .order('name')

  if (!donors || donors.length === 0) return []

  // Group by entity_slug.  Pick the longest name as display_name (heuristic:
  // the longest form is usually the most descriptive, less prone to truncation).
  type SlugGroup = {
    slug: string
    entity_type: string
    display_name: string
    donor_ids: string[]
    total_contributed: number
    distinct_recipients: number
    max_span_days: number | null
  }
  const groups = new Map<string, SlugGroup>()
  for (const d of donors) {
    const slug = d.entity_slug as string
    const existing = groups.get(slug)
    if (existing) {
      existing.donor_ids.push(d.id as string)
      existing.total_contributed += d.total_contributed ?? 0
      existing.distinct_recipients = Math.max(existing.distinct_recipients, d.distinct_recipients ?? 0)
      if ((d.contribution_span_days ?? 0) > (existing.max_span_days ?? 0)) {
        existing.max_span_days = d.contribution_span_days
      }
      if ((d.name as string).length > existing.display_name.length) {
        existing.display_name = d.name as string
      }
    } else {
      groups.set(slug, {
        slug,
        entity_type: d.entity_type as string,
        display_name: d.name as string,
        donor_ids: [d.id as string],
        total_contributed: d.total_contributed ?? 0,
        distinct_recipients: d.distinct_recipients ?? 0,
        max_span_days: d.contribution_span_days,
      })
    }
  }

  // Fetch contribution date bounds for each group (donors.total_contributed
  // is pre-aggregated but doesn't include date range for the merged group).
  // No date filter — these are small per-org result sets and all-time means all-time.
  const allDonorIds = Array.from(groups.values()).flatMap((g) => g.donor_ids)
  const { data: dateRows } = await supabase
    .from('contributions')
    .select('donor_id, contribution_date, amount')
    .in('donor_id', allDonorIds)
    .eq('city_fips', cityFips)
    .range(0, 99999)

  // Track per-group dates and election-cycle totals from the same bounded
  // result set. Keeping this aggregation here avoids one query per directory
  // card when /unions applies the shared cycle filter.
  const donorToSlug = new Map<string, string>()
  for (const group of groups.values()) {
    for (const donorId of group.donor_ids) donorToSlug.set(donorId, group.slug)
  }
  const currentCycle = currentElectionCycle()
  const currentCycleBySlug = new Map<string, number>()
  const cycleTotalsBySlug = new Map<string, Map<number, number>>()

  if (dateRows) {
    for (const r of dateRows) {
      const donorId = r.donor_id as string
      const date = r.contribution_date as string | null
      const amount = Number(r.amount ?? 0)
      if (!date) continue
      const slug = donorToSlug.get(donorId)
      if (!slug) continue
      const group = groups.get(slug)
      if (!group) continue

      const groupWithDates = group as SlugGroup & {
        earliest?: string
        latest?: string
      }
      if (!groupWithDates.earliest || date < groupWithDates.earliest) {
        groupWithDates.earliest = date
      }
      if (!groupWithDates.latest || date > groupWithDates.latest) {
        groupWithDates.latest = date
      }

      const cycle = cycleOf(date)
      if (cycle === null) continue
      const totals = cycleTotalsBySlug.get(slug) ?? new Map<number, number>()
      totals.set(cycle, (totals.get(cycle) ?? 0) + amount)
      cycleTotalsBySlug.set(slug, totals)
      if (cycle === currentCycle) {
        currentCycleBySlug.set(slug, (currentCycleBySlug.get(slug) ?? 0) + amount)
      }
    }
  }

  const cycleWindow = [
    currentCycle - 8,
    currentCycle - 6,
    currentCycle - 4,
    currentCycle - 2,
    currentCycle,
  ]

  const result: OrgAggregate[] = []
  for (const g of groups.values()) {
    if (g.total_contributed <= 0) continue
    const gExt = g as SlugGroup & { earliest?: string; latest?: string }
    result.push({
      slug: g.slug,
      display_name: g.display_name,
      entity_type: g.entity_type,
      donor_ids: g.donor_ids,
      total_contributed: g.total_contributed,
      current_cycle_total: currentCycleBySlug.get(g.slug) ?? 0,
      recipient_count: g.distinct_recipients,
      earliest_contribution_date: gExt.earliest ?? null,
      latest_contribution_date: gExt.latest ?? null,
      sponsor_disclosure: inferOrgDisclosure(g.display_name),
      cycle_bars: cycleWindow.map((cycle) => ({
        cycle,
        total: cycleTotalsBySlug.get(g.slug)?.get(cycle) ?? 0,
      })),
    })
  }

  return result.sort((a, b) => {
    // Primary: current cycle total.  Secondary: all-time total.
    const da = b.current_cycle_total - a.current_cycle_total
    if (da !== 0) return da
    return b.total_contributed - a.total_contributed
  })
}

// ─── Profile ────────────────────────────────────────────────────────────

export async function getOrgBySlug(
  slug: string,
  cityFips = RICHMOND_FIPS,
): Promise<OrgAggregate | null> {
  const all = await getOrgList(cityFips)
  return all.find((o) => o.slug === slug) ?? null
}

/** All contributions FROM this org (as a donor) TO committees.
 *  Joins contributions → committees to surface recipient context. */
export async function getOrgOutgoing(
  donorIds: string[],
  cityFips = RICHMOND_FIPS,
): Promise<OrgOutgoingRow[]> {
  if (donorIds.length === 0) return []

  const { data } = await supabase
    .from('contributions')
    .select(
      'amount, contribution_date, contribution_type, filing_id, committees!inner(id, name, candidate_name)',
    )
    .in('donor_id', donorIds)
    .eq('city_fips', cityFips)
    .order('contribution_date', { ascending: false })
    .range(0, 19999)

  if (!data) return []
  return data.map((row) => {
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

/** Per-cycle aggregates for the timeline layer.
 *  Returns one row per cycle with total_out (money FROM this org). */
export async function getOrgCycleBars(
  donorIds: string[],
  cityFips = RICHMOND_FIPS,
): Promise<Array<{ cycle: number; total: number }>> {
  if (donorIds.length === 0) return []

  const { data } = await supabase
    .from('contributions')
    .select('amount, contribution_date')
    .in('donor_id', donorIds)
    .eq('city_fips', cityFips)
    .range(0, 99999)

  if (!data) return []

  const buckets = new Map<number, number>()
  for (const r of data) {
    const cycle = cycleOf(r.contribution_date as string | null)
    if (cycle === null) continue
    buckets.set(cycle, (buckets.get(cycle) ?? 0) + Number(r.amount ?? 0))
  }

  return Array.from(buckets.entries())
    .map(([cycle, total]) => ({ cycle, total }))
    .sort((a, b) => a.cycle - b.cycle)
}

/** Independent expenditures filed BY this org (name-matched against
 *  `independent_expenditures.committee_name`).  Reuses the PAC pattern:
 *  exact ILIKE match on the org's display name.
 *
 *  ponytail: this is the same loose-match pattern getPACIndependentExpenditures
 *  uses.  When entity resolution (S26) lands, both should switch to a
 *  committee_id FK. */
export async function getOrgIndependentExpenditures(
  displayName: string,
  cityFips = RICHMOND_FIPS,
): Promise<PACIndependentExpenditureRow[]> {
  if (!displayName) return []

  const { data } = await supabase
    .from('independent_expenditures')
    .select(
      'candidate_name, support_or_oppose, amount, expenditure_date, payee_name, description, expenditure_code, filing_id',
    )
    .eq('city_fips', cityFips)
    .ilike('committee_name', displayName)
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
