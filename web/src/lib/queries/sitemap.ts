import { RICHMOND_FIPS, supabase } from './_shared'

const COLS_SITEMAP_AGENDA_ITEM =
  'meeting_id, item_number, meetings!inner(meeting_date, city_fips, source_cancelled_at)'

/**
 * The approved rolling sitemap must fail closed before it can silently hit
 * Supabase's 10,000-row response ceiling.
 */
const MAX_AGENDA_ITEM_SITEMAP_ROWS = 10_000
const MAX_COMPLETE_SITEMAP_ROWS = 10_000

const COLS_SITEMAP_MEETING = 'id'
const COLS_SITEMAP_OFFICIAL = 'name'
const COLS_SITEMAP_ELECTION = 'election_date, election_type, updated_at'
const COLS_SITEMAP_COMMISSION = 'id, created_at, last_website_scrape'
const COLS_SITEMAP_ENTITY = 'entity_slug, created_at'
// Mirror the roles publicly eligible on /council. The sitemap test pins this
// explicit set so adding a new role requires a deliberate discovery decision.
const SITEMAP_COUNCIL_ROLES = [
  'mayor', 'vice_mayor', 'councilmember', 'council_member', 'City/Town Council Member',
]

export interface SitemapMeetingRow {
  id: string
}

export interface SitemapOfficialRow {
  name: string
}

export interface SitemapElectionRow {
  election_date: string
  election_type: 'primary' | 'general' | 'special' | 'runoff'
  updated_at: string
}

export interface SitemapCommissionRow {
  id: string
  last_modified: string
}

export interface SitemapEntitySlugRow {
  slug: string
  created_at: string
}

export interface SitemapAgendaItemRow {
  meeting_id: string
  item_number: string
  meeting_date: string
}

function completeRows<T>(
  dataset: string,
  data: T[] | null,
  count: number | null,
): T[] {
  if (count === null) {
    throw new Error(`${dataset} query did not return an exact row count.`)
  }
  if (count >= MAX_COMPLETE_SITEMAP_ROWS) {
    throw new Error(
      `${dataset} reached ${MAX_COMPLETE_SITEMAP_ROWS.toLocaleString('en-US')} rows.`,
    )
  }
  const rows = data ?? []
  if (rows.length !== count) {
    throw new Error(
      `${dataset} query returned ${rows.length.toLocaleString('en-US')} of ${count.toLocaleString('en-US')} rows.`,
    )
  }
  return rows
}

function failSitemapQuery(dataset: string, error: unknown): never {
  console.error(`${dataset} query failed:`, error)
  throw error
}

function uniqueEntitySlugs(
  rows: Array<{ entity_slug: string | null; created_at: string }>,
): SitemapEntitySlugRow[] {
  const bySlug = new Map<string, SitemapEntitySlugRow>()
  for (const row of rows) {
    if (!row.entity_slug) continue
    const existing = bySlug.get(row.entity_slug)
    if (!existing || row.created_at > existing.created_at) {
      bySlug.set(row.entity_slug, {
        slug: row.entity_slug,
        created_at: row.created_at,
      })
    }
  }
  return Array.from(bySlug.values())
}

export async function getSitemapMeetings(
  cityFips = RICHMOND_FIPS,
): Promise<SitemapMeetingRow[]> {
  const { data, error, count } = await supabase
    .from('meetings')
    .select(COLS_SITEMAP_MEETING, { count: 'exact' })
    .eq('city_fips', cityFips)
    .limit(MAX_COMPLETE_SITEMAP_ROWS)
    .order('id')

  if (error) failSitemapQuery('Meeting sitemap', error)
  return completeRows('Meeting sitemap', data, count) as SitemapMeetingRow[]
}

/** Only current council members are publicly linked from /council. */
export async function getSitemapOfficials(
  cityFips = RICHMOND_FIPS,
): Promise<SitemapOfficialRow[]> {
  const { data, error, count } = await supabase
    .from('officials')
    .select(COLS_SITEMAP_OFFICIAL, { count: 'exact' })
    .eq('city_fips', cityFips)
    .eq('is_current', true)
    .in('role', SITEMAP_COUNCIL_ROLES)
    .limit(MAX_COMPLETE_SITEMAP_ROWS)
    .order('id')

  if (error) failSitemapQuery('Council sitemap', error)
  return completeRows('Council sitemap', data, count) as SitemapOfficialRow[]
}

export async function getSitemapElections(
  cityFips = RICHMOND_FIPS,
): Promise<SitemapElectionRow[]> {
  const { data, error, count } = await supabase
    .from('elections')
    .select(COLS_SITEMAP_ELECTION, { count: 'exact' })
    .eq('city_fips', cityFips)
    .limit(MAX_COMPLETE_SITEMAP_ROWS)
    .order('id')

  if (error) failSitemapQuery('Election sitemap', error)
  return completeRows('Election sitemap', data, count) as SitemapElectionRow[]
}

export async function getSitemapCommissions(
  cityFips = RICHMOND_FIPS,
): Promise<SitemapCommissionRow[]> {
  const { data, error, count } = await supabase
    .from('commissions')
    .select(COLS_SITEMAP_COMMISSION, { count: 'exact' })
    .eq('city_fips', cityFips)
    .limit(MAX_COMPLETE_SITEMAP_ROWS)
    .order('id')

  if (error) failSitemapQuery('Commission sitemap', error)
  return completeRows('Commission sitemap', data, count).map((row) => ({
    id: row.id,
    last_modified: row.last_website_scrape ?? row.created_at,
  }))
}

/** Public individual profiles already enforce this threshold in getDonorList. */
export async function getSitemapDonorSlugs(
  cityFips = RICHMOND_FIPS,
): Promise<SitemapEntitySlugRow[]> {
  const { data, error, count } = await supabase
    .from('donors')
    .select(COLS_SITEMAP_ENTITY, { count: 'exact' })
    .eq('city_fips', cityFips)
    .eq('entity_type', 'person')
    .gte('total_contributed', 5_000)
    .not('entity_slug', 'is', null)
    .limit(MAX_COMPLETE_SITEMAP_ROWS)
    .order('id')

  if (error) failSitemapQuery('Individual-donor sitemap', error)
  return uniqueEntitySlugs(
    completeRows('Individual-donor sitemap', data, count),
  )
}

/** Union/corporation profiles are public only when their grouped giving is nonzero. */
export async function getSitemapOrganizationSlugs(
  cityFips = RICHMOND_FIPS,
): Promise<SitemapEntitySlugRow[]> {
  const { data, error, count } = await supabase
    .from('donors')
    .select(COLS_SITEMAP_ENTITY, { count: 'exact' })
    .eq('city_fips', cityFips)
    .in('entity_type', ['union', 'corporation'])
    .gt('total_contributed', 0)
    .not('entity_slug', 'is', null)
    .limit(MAX_COMPLETE_SITEMAP_ROWS)
    .order('id')

  if (error) failSitemapQuery('Organization sitemap', error)
  return uniqueEntitySlugs(
    completeRows('Organization sitemap', data, count),
  )
}

/**
 * Load every active agenda item in the bounded sitemap window.
 *
 * `count: exact` plus the length check makes a response-cap change visible:
 * a partial sitemap is rejected instead of being published as complete.
 */
export async function getRecentAgendaItemSlugs(
  meetingDateCutoff: string,
  cityFips = RICHMOND_FIPS,
): Promise<SitemapAgendaItemRow[]> {
  const { data, error, count } = await supabase
    .from('agenda_items')
    .select(COLS_SITEMAP_AGENDA_ITEM, { count: 'exact' })
    .is('agenda_source_retired_at', null)
    .is('meetings.source_cancelled_at', null)
    .eq('meetings.city_fips', cityFips)
    .gte('meetings.meeting_date', meetingDateCutoff)
    .order('id')

  if (error) {
    console.error('getRecentAgendaItemSlugs query failed:', error)
    throw error
  }
  if (count === null) {
    throw new Error('Agenda-item sitemap query did not return an exact row count.')
  }
  if (count >= MAX_AGENDA_ITEM_SITEMAP_ROWS) {
    throw new Error(
      `Rolling agenda-item sitemap dataset reached ${MAX_AGENDA_ITEM_SITEMAP_ROWS.toLocaleString('en-US')} rows.`,
    )
  }

  const rows = data ?? []
  if (rows.length !== count) {
    throw new Error(
      `Agenda-item sitemap query returned ${rows.length.toLocaleString('en-US')} of ${count.toLocaleString('en-US')} rows.`,
    )
  }

  return rows.map((row) => {
    const meeting = row.meetings as unknown as { meeting_date: string }
    return {
      meeting_id: row.meeting_id as string,
      item_number: row.item_number as string,
      meeting_date: meeting.meeting_date,
    }
  })
}
