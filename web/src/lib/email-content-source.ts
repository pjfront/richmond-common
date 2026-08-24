import type { Provenance } from './types'

/**
 * Columns required to choose the persisted recap artifact and its matching
 * provenance. Keep recap, digest, and recovery callers on this projection so
 * they cannot silently diverge on source preference.
 */
export const RECAP_SOURCE_COLUMNS = [
  'id',
  'city_fips',
  'meeting_date',
  'meeting_type',
  'meeting_recap',
  'meeting_recap_provenance',
  'transcript_recap',
  'transcript_recap_provenance',
  'minutes_url',
  'recap_emailed_at',
  'transcript_recap_emailed_at',
  'source_cancelled_at',
].join(', ')

export interface PersistedRecapSource {
  id: string
  city_fips: string
  meeting_date: string
  meeting_type: string
  meeting_recap: string | null
  meeting_recap_provenance: Provenance | null
  transcript_recap: string | null
  transcript_recap_provenance: Provenance | null
  minutes_url: string | null
  recap_emailed_at: string | null
  transcript_recap_emailed_at: string | null
  source_cancelled_at: string | null
}

export interface SelectedPersistedRecap {
  id: string
  meeting_date: string
  meeting_type: string
  meeting_recap: string
  minutes_url: string | null
  meeting_recap_provenance: Provenance | null
  source: 'minutes' | 'transcript'
  recap_emailed_at: string | null
  transcript_recap_emailed_at: string | null
}

function nonBlank(value: string | null): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

/**
 * Select the source-closest persisted recap narrative.
 *
 * Official-minutes recap wins when present. A transcript recap is the only
 * fallback, and each artifact always travels with its own provenance column.
 * Cancelled source meetings never produce email content.
 */
export function selectPersistedRecap(
  meeting: PersistedRecapSource,
): SelectedPersistedRecap | null {
  if (meeting.source_cancelled_at) return null

  if (nonBlank(meeting.meeting_recap)) {
    return {
      id: meeting.id,
      meeting_date: meeting.meeting_date,
      meeting_type: meeting.meeting_type,
      meeting_recap: meeting.meeting_recap,
      minutes_url: meeting.minutes_url,
      meeting_recap_provenance: meeting.meeting_recap_provenance,
      source: 'minutes',
      recap_emailed_at: meeting.recap_emailed_at,
      transcript_recap_emailed_at: meeting.transcript_recap_emailed_at,
    }
  }

  if (nonBlank(meeting.transcript_recap)) {
    return {
      id: meeting.id,
      meeting_date: meeting.meeting_date,
      meeting_type: meeting.meeting_type,
      meeting_recap: meeting.transcript_recap,
      minutes_url: meeting.minutes_url,
      meeting_recap_provenance: meeting.transcript_recap_provenance,
      source: 'transcript',
      recap_emailed_at: meeting.recap_emailed_at,
      transcript_recap_emailed_at: meeting.transcript_recap_emailed_at,
    }
  }

  return null
}
