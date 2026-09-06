/** Counts describe the displayed records, never attendance or policy support. */
export interface ObservedVoteRecord {
  id: string
  motion_id?: string
  meeting_id: string
  agenda_item_id?: string
  meeting_date: string
  vote_choice: string
}

export function recordedDate(value: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
  const date = new Date(`${value}T00:00:00Z`)
  return Number.isFinite(date.valueOf()) && date.toISOString().slice(0, 10) === value ? value : null
}

/** Only identical source-row repetitions collapse; similar motions stay distinct. */
export function uniqueObservedVoteRecords<T extends ObservedVoteRecord>(records: readonly T[]): T[] {
  const seen = new Map<string, T>()
  for (const record of records) {
    if (!record.id || !record.meeting_id) throw new Error('Voting record identity missing')
    const previous = seen.get(record.id)
    if (previous) {
      for (const key of ['motion_id', 'meeting_id', 'agenda_item_id', 'meeting_date', 'vote_choice'] as const) {
        if (previous[key] !== record[key]) throw new Error('Repeated voting record has conflicting evidence')
      }
    } else seen.set(record.id, record)
  }
  return [...seen.values()]
}

export function observedVoteSummary(records: readonly ObservedVoteRecord[]) {
  const unique = uniqueObservedVoteRecords(records)
  const dates = unique.map(row => recordedDate(row.meeting_date)).filter((day): day is string => day !== null).sort()
  return {
    recordCount: unique.length,
    itemCount: new Set(unique.map(row => row.agenda_item_id ? `${row.meeting_id}:${row.agenda_item_id}` : `record:${row.id}`)).size,
    meetingCount: new Set(unique.map(row => row.meeting_id)).size,
    firstDate: dates[0] ?? null,
    lastDate: dates.at(-1) ?? null,
    undatedCount: unique.length - dates.length,
  }
}

/** The profile query is for exactly one official. Repeated source rows do not create another motion. */
export function officialMotionRecords<T extends ObservedVoteRecord>(records: readonly T[]) {
  const groups = new Map<string, T[]>()
  for (const record of uniqueObservedVoteRecords(records)) {
    const key = record.motion_id ? `${record.meeting_id}:${record.motion_id}` : `record:${record.id}`
    const group = groups.get(key) ?? []
    if (group.length && (group[0].agenda_item_id !== record.agenda_item_id || group[0].meeting_date !== record.meeting_date)) {
      throw new Error('Repeated motion has conflicting agenda or date evidence')
    }
    group.push(record)
    groups.set(key, group)
  }
  return [...groups.values()].map(group => normalizeMotionVotes(group, () => 'this-profile-official')[0])
}

export function formatObservedDate(day: string): string {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' })
}
import { normalizeMotionVotes } from './vote-records'
