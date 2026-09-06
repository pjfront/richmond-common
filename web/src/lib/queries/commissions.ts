import { fetchMeetingCounts, applyMeetingCounts } from './meetings'
import { readCompleteRecords } from '../complete-record-read'
import { supabase, RICHMOND_FIPS, warnIfEmpty, COLS_MEETING_LIST, COLS_COMMISSION, COLS_CURRENT_COMMISSION_MEMBER, COLS_COMMISSION_MEMBER } from './_shared'
import type { Meeting, Commission, CommissionMember, CommissionWithStats, CommissionStaleness, MeetingWithCounts, NeighborhoodCouncil } from '../types'

export async function getCommissions(
  cityFips = RICHMOND_FIPS
): Promise<CommissionWithStats[]> {
  const { data: commissions, count, error } = await supabase
    .from('commissions')
    .select(COLS_COMMISSION, { count: 'exact' })
    .eq('city_fips', cityFips)
    .order('name').order('id').limit(100)

  if (error || !commissions || count === null || count > 100 || commissions.length !== count) {
    throw new Error('Commission roster unavailable or incomplete')
  }
  warnIfEmpty('getCommissions', commissions)

  const commissionIds = (commissions ?? []).map((c) => c.id)
  if (commissionIds.length === 0) return []

  // Count current members per commission, separating active-term from holdovers
  const { data: members, count: memberCount, error: memberError } = await supabase
    .from('commission_members')
    .select(COLS_CURRENT_COMMISSION_MEMBER, { count: 'exact' })
    .in('commission_id', commissionIds)
    .eq('is_current', true).order('id').limit(1000)
  if (memberError || !members || memberCount === null || memberCount > 1000 || members.length !== memberCount) {
    throw new Error('Current commission membership unavailable or incomplete')
  }

  const today = new Date().toISOString().split('T')[0]
  const activeCountMap = new Map<string, number>()
  const holdoverCountMap = new Map<string, number>()
  for (const m of members ?? []) {
    const isExpired = m.term_end && m.term_end < today
    if (isExpired) {
      holdoverCountMap.set(m.commission_id, (holdoverCountMap.get(m.commission_id) ?? 0) + 1)
    } else {
      activeCountMap.set(m.commission_id, (activeCountMap.get(m.commission_id) ?? 0) + 1)
    }
  }

  return (commissions ?? []).map((c) => {
    const commission = c as Commission
    const activeCount = activeCountMap.get(commission.id) ?? 0
    const holdoverCount = holdoverCountMap.get(commission.id) ?? 0
    return {
      ...commission,
      member_count: activeCount,
      holdover_count: holdoverCount,
    }
  })
}

export async function getCommission(
  commissionId: string,
  cityFips = RICHMOND_FIPS
): Promise<{ commission: Commission; members: CommissionMember[] } | null> {
  const { data: commission, error } = await supabase
    .from('commissions')
    .select(COLS_COMMISSION)
    .eq('id', commissionId)
    .eq('city_fips', cityFips)
    .maybeSingle()

  if (error) throw new Error('Commission details unavailable')
  if (!commission) return null

  const { data: members, count: memberCount, error: memberError } = await supabase
    .from('commission_members')
    .select(COLS_COMMISSION_MEMBER, { count: 'exact' })
    .eq('commission_id', commissionId)
    .eq('is_current', true)
    .order('name').order('id').limit(100)
  if (memberError || !members || memberCount === null || memberCount > 100 || members.length !== memberCount) {
    throw new Error('Commission detail membership unavailable or incomplete')
  }

  return {
    commission: commission as Commission,
    members: (members ?? []) as CommissionMember[],
  }
}

export async function getCommissionStaleness(
  cityFips = RICHMOND_FIPS
): Promise<CommissionStaleness[]> {
  const { data, error } = await supabase
    .from('v_commission_staleness')
    .select('*')
    .eq('city_fips', cityFips)

  if (error) {
    console.error('getCommissionStaleness query failed:', error)
    return [] as CommissionStaleness[]
  }
  return (data ?? []) as CommissionStaleness[]
}

export async function getCommissionMeetings(
  commissionId: string,
  cityFips = RICHMOND_FIPS
): Promise<MeetingWithCounts[]> {
  // commission_id is not unique on bodies (migration 035); preserve every
  // exact linked body rather than treating a multiple-row error as no meetings.
  const bodies = await readCompleteRecords('Commission meeting bodies', (from, to) => supabase.from('bodies')
    .select('id', { count: 'exact' }).eq('commission_id', commissionId).eq('city_fips', cityFips)
    .order('id').range(from, to), { maxRows: 100 })
  if (!bodies.length) return []

  const [meetings, countMap] = await Promise.all([
    readCompleteRecords('Commission meetings', (from, to) => supabase.from('meetings')
      .select(COLS_MEETING_LIST, { count: 'exact' }).in('body_id', bodies.map(body => body.id))
      .eq('city_fips', cityFips).order('meeting_date', { ascending: false }).order('id').range(from, to)),
    fetchMeetingCounts(cityFips),
  ])
  return applyMeetingCounts(meetings as Meeting[], countMap)
}


// ─── Neighborhood Councils ─────────────────────────────────────────────────

const COLS_NEIGHBORHOOD_COUNCIL =
  'id, city_fips, name, short_name, nc_type, geojson_codes, is_active, ' +
  'meeting_schedule, meeting_time, meeting_location, city_page_url, ' +
  'city_page_id, document_center_path, contact_email, president, ' +
  'vice_president, notes, created_at, updated_at'

export async function getNeighborhoodCouncils(
  cityFips = RICHMOND_FIPS
): Promise<NeighborhoodCouncil[]> {
  const { data, error } = await supabase
    .from('neighborhood_councils')
    .select(COLS_NEIGHBORHOOD_COUNCIL)
    .eq('city_fips', cityFips)
    .order('name')

  if (error) {
    console.error('getNeighborhoodCouncils query failed:', error)
    return []
  }
  return (data ?? []) as unknown as NeighborhoodCouncil[]
}
