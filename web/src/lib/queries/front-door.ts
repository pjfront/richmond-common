import { cache } from 'react'
import type { Election } from '../types'
import {
  COLS_ELECTION_FRONT_DOOR,
  COLS_FRONT_DOOR_SOURCE_DOCUMENT,
  COLS_MEETING_FRONT_DOOR,
  RICHMOND_FIPS,
  supabase,
} from './_shared'

export type FrontDoorReadResult<T> =
  | { state: 'ready'; data: T }
  | { state: 'empty'; data: null }
  | { state: 'error'; data: null }

export interface FrontDoorMeeting {
  id: string
  meeting_date: string
  meeting_type: string
  source_url: string
  source_observed_at: string
  body_name: string | null
}

export interface FrontDoorElection extends Omit<Election, 'source_tier' | 'source_url'> {
  source_tier: 1 | 2
  source_url: string
}

type FrontDoorMeetingRow = {
  id: string
  meeting_date: string
  meeting_type: string
  agenda_url: string | null
  source_meeting_guid: string | null
  bodies: { name: string } | null
}

type FrontDoorSourceDocumentRow = {
  ingested_at: string
  source_url: string | null
}

function publicElection(election: Election | null): FrontDoorElection | null {
  if (
    !election
    || (election.source_tier !== 1 && election.source_tier !== 2)
    || !election.source_url?.trim()
  ) {
    return null
  }

  return {
    ...election,
    source_tier: election.source_tier,
    source_url: election.source_url.trim(),
  }
}

async function getUpcomingElectionRecordQuery(
  cityFips = RICHMOND_FIPS,
): Promise<FrontDoorReadResult<Election>> {
  const today = new Date().toISOString().split('T')[0]
  const { data, error } = await supabase
    .from('elections')
    .select(COLS_ELECTION_FRONT_DOOR)
    .eq('city_fips', cityFips)
    .gte('election_date', today)
    .order('election_date', { ascending: true })
    .limit(1)
    .abortSignal(AbortSignal.timeout(10_000))
    .maybeSingle()

  if (error) {
    console.error('getUpcomingElection query failed:', error)
    return { state: 'error', data: null }
  }
  if (!data) return { state: 'empty', data: null }
  return { state: 'ready', data: data as Election }
}

const getUpcomingElectionRecord = cache(getUpcomingElectionRecordQuery)

/** Compatibility read for existing election surfaces; failures remain null. */
export const getUpcomingElection = cache(async (
  cityFips = RICHMOND_FIPS,
): Promise<Election | null> => {
  const result = await getUpcomingElectionRecord(cityFips)
  return result.state === 'ready' ? result.data : null
})

async function getFrontDoorElectionQuery(
  cityFips = RICHMOND_FIPS,
): Promise<FrontDoorReadResult<FrontDoorElection>> {
  const result = await getUpcomingElectionRecord(cityFips)
  if (result.state !== 'ready') return result

  const election = publicElection(result.data)
  return election
    ? { state: 'ready', data: election }
    : { state: 'empty', data: null }
}

/** One memoized, provenance-gated election read shared by the homepage and nav. */
export const getFrontDoorElection = cache(getFrontDoorElectionQuery)

async function sourceObservationForMeeting(
  row: FrontDoorMeetingRow,
  cityFips: string,
): Promise<FrontDoorReadResult<FrontDoorMeeting>> {
  if (!row.agenda_url?.trim()) return { state: 'empty', data: null }

  let query = supabase
    .from('documents')
    .select(COLS_FRONT_DOOR_SOURCE_DOCUMENT)
    .eq('city_fips', cityFips)
    .eq('source_type', 'escribemeetings')
    .eq('credibility_tier', 1)
    .is('source_retired_at', null)

  query = query.contains('metadata', {
    source_observation_state: 'complete_agenda',
    ...(row.source_meeting_guid ? { meeting_guid: row.source_meeting_guid } : {}),
  })
  if (!row.source_meeting_guid) query = query.eq('source_url', row.agenda_url)

  const { data, error } = await query
    .order('ingested_at', { ascending: false })
    .limit(1)
    .abortSignal(AbortSignal.timeout(10_000))
    .maybeSingle()

  if (error) {
    console.error('getFrontDoorMeeting source observation query failed:', error)
    return { state: 'error', data: null }
  }

  const source = data as FrontDoorSourceDocumentRow | null
  if (!source?.ingested_at) return { state: 'empty', data: null }

  return {
    state: 'ready',
    data: {
      id: row.id,
      meeting_date: row.meeting_date,
      meeting_type: row.meeting_type,
      source_url: source.source_url?.trim() || row.agenda_url,
      source_observed_at: source.ingested_at,
      body_name: row.bodies?.name ?? null,
    },
  }
}

/**
 * Return the next non-cancelled meeting backed by its active official agenda
 * observation. When none is scheduled, use the latest past meeting with the
 * same source-closest timestamp contract.
 */
export async function getFrontDoorMeeting(
  cityFips = RICHMOND_FIPS,
): Promise<FrontDoorReadResult<FrontDoorMeeting>> {
  const today = new Date().toISOString().split('T')[0]
  const { data: upcoming, error: upcomingError } = await supabase
    .from('meetings')
    .select(COLS_MEETING_FRONT_DOOR)
    .eq('city_fips', cityFips)
    .is('source_cancelled_at', null)
    .not('agenda_url', 'is', null)
    .neq('agenda_url', '')
    .gte('meeting_date', today)
    .order('meeting_date', { ascending: true })
    .limit(1)
    .abortSignal(AbortSignal.timeout(10_000))
    .maybeSingle()

  if (upcomingError) {
    console.error('getFrontDoorMeeting upcoming query failed:', upcomingError)
    return { state: 'error', data: null }
  }

  if (upcoming) {
    return sourceObservationForMeeting(
      upcoming as unknown as FrontDoorMeetingRow,
      cityFips,
    )
  }

  const { data: latest, error: latestError } = await supabase
    .from('meetings')
    .select(COLS_MEETING_FRONT_DOOR)
    .eq('city_fips', cityFips)
    .is('source_cancelled_at', null)
    .not('agenda_url', 'is', null)
    .neq('agenda_url', '')
    .lt('meeting_date', today)
    .order('meeting_date', { ascending: false })
    .limit(1)
    .abortSignal(AbortSignal.timeout(10_000))
    .maybeSingle()

  if (latestError) {
    console.error('getFrontDoorMeeting latest query failed:', latestError)
    return { state: 'error', data: null }
  }
  if (!latest) return { state: 'empty', data: null }

  return sourceObservationForMeeting(
    latest as unknown as FrontDoorMeetingRow,
    cityFips,
  )
}
