import { supabase, RICHMOND_FIPS } from './_shared'
import { COUNCIL_ROLES } from './council'
import type { ElectionType } from '../types'

const COLS_SITEMAP_MEETING = 'id, meeting_date'
const COLS_SITEMAP_ITEM = 'id, meeting_id, item_number, meetings!inner(meeting_date, city_fips)'
const COLS_SITEMAP_OFFICIAL = 'id, name'
const COLS_SITEMAP_ELECTION = 'id, election_date, election_type, updated_at'

export interface SitemapMeetingRow {
  id: string
  meeting_date: string
}

export interface SitemapAgendaItemRow {
  meeting_id: string
  item_number: string
  meeting_date: string
}

export interface SitemapOfficialRow {
  name: string
}

export interface SitemapElectionRow {
  election_date: string
  election_type: ElectionType
  updated_at: string
}

export async function getSitemapMeetingsPage(
  from: number,
  to: number,
  cityFips = RICHMOND_FIPS,
): Promise<SitemapMeetingRow[]> {
  const { data, error } = await supabase
    .from('meetings')
    .select(COLS_SITEMAP_MEETING)
    .eq('city_fips', cityFips)
    .order('id')
    .range(from, to)

  if (error) {
    console.error('getSitemapMeetingsPage query failed:', error)
    throw new Error('Failed to load meeting sitemap rows')
  }
  return (data ?? []) as SitemapMeetingRow[]
}

export async function getSitemapAgendaItemsPage(
  from: number,
  to: number,
  cityFips = RICHMOND_FIPS,
): Promise<SitemapAgendaItemRow[]> {
  const { data, error } = await supabase
    .from('agenda_items')
    .select(COLS_SITEMAP_ITEM)
    .is('agenda_source_retired_at', null)
    .eq('meetings.city_fips', cityFips)
    .order('id')
    .range(from, to)

  if (error) {
    console.error('getSitemapAgendaItemsPage query failed:', error)
    throw new Error('Failed to load agenda-item sitemap rows')
  }

  return (data ?? []).map((row) => {
    const meeting = row.meetings as unknown as { meeting_date: string }
    return {
      meeting_id: row.meeting_id,
      item_number: row.item_number,
      meeting_date: meeting.meeting_date,
    }
  })
}

export async function getSitemapOfficialsPage(
  from: number,
  to: number,
  cityFips = RICHMOND_FIPS,
): Promise<SitemapOfficialRow[]> {
  const { data, error } = await supabase
    .from('officials')
    .select(COLS_SITEMAP_OFFICIAL)
    .eq('city_fips', cityFips)
    .in('role', COUNCIL_ROLES)
    .order('id')
    .range(from, to)

  if (error) {
    console.error('getSitemapOfficialsPage query failed:', error)
    throw new Error('Failed to load official sitemap rows')
  }
  return (data ?? []) as SitemapOfficialRow[]
}

export async function getSitemapElectionsPage(
  from: number,
  to: number,
  cityFips = RICHMOND_FIPS,
): Promise<SitemapElectionRow[]> {
  const { data, error } = await supabase
    .from('elections')
    .select(COLS_SITEMAP_ELECTION)
    .eq('city_fips', cityFips)
    .order('id')
    .range(from, to)

  if (error) {
    console.error('getSitemapElectionsPage query failed:', error)
    throw new Error('Failed to load election sitemap rows')
  }
  return (data ?? []) as SitemapElectionRow[]
}
