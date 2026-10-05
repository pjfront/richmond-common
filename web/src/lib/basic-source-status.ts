/** Public refresh metadata describes a bounded source check, never complete coverage. */
export const BASIC_SOURCE_FEATURES = ['agenda_refresh', 'finance'] as const
export type BasicSourceFeature = typeof BASIC_SOURCE_FEATURES[number]
export type BasicSourceState = 'checked' | 'partial' | 'pending_review' | 'never_checked' | 'unavailable'

export interface CoreProjectionStatusRow {
  feature: string
  status: string
  checked_at: string | null
  source_scope: string | null
}

export interface BasicSourceCheck {
  feature: BasicSourceFeature
  state: BasicSourceState
  checkedAt: string | null
  scope: string | null
}

export type BasicSourceStatus = Record<BasicSourceFeature, BasicSourceCheck>

function checkedTimestamp(value: string | null, now: number): string | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(value)) return null
  const timestamp = Date.parse(value)
  if (!Number.isFinite(timestamp) || timestamp > now + 5 * 60_000) return null
  return new Date(timestamp).toISOString()
}

export function basicSourceStatus(rows: CoreProjectionStatusRow[] | null, now = Date.now()): BasicSourceStatus {
  function source(feature: BasicSourceFeature): BasicSourceCheck {
    const base = { feature, checkedAt: null, scope: null }
    if (rows === null) return { ...base, state: 'unavailable' }
    const matches = rows.filter(row => row.feature === feature)
    if (!matches.length) return { ...base, state: 'never_checked' }
    if (matches.length !== 1) return { ...base, state: 'unavailable' }
    const row = matches[0]
    const scope = row.source_scope === 'past-60/next-14-day window' || row.source_scope === '0660620:calendar-2026' ? row.source_scope : null
    const checkedAt = checkedTimestamp(row.checked_at, now)
    // Rollover is a review state, not a successful refresh. Keep its last
    // recorded check visible without describing the figures as current.
    if (feature === 'finance' && row.status === 'pending_review') return { feature, state: 'pending_review', checkedAt, scope }
    const supported = feature === 'finance' ? row.status === 'partial' : ['checked', 'partial'].includes(row.status)
    if (!supported || (row.checked_at && !checkedAt)) return { ...base, state: 'unavailable' }
    if (!checkedAt) return { ...base, state: 'never_checked', scope }
    return { feature, state: row.status as 'checked' | 'partial', checkedAt, scope }
  }
  return { agenda_refresh: source('agenda_refresh'), finance: source('finance') }
}

export function basicSourceScope(check: BasicSourceCheck): string {
  if (check.feature === 'agenda_refresh' && check.scope === 'past-60/next-14-day window') return 'Past 60 days and next 14 days only; some agendas may be missing.'
  if (check.feature === 'finance' && check.scope === '0660620:calendar-2026') return 'Partial electronic index: January 1–November 3, 2026.'
  return 'The checked source window is not established.'
}

export function formatSourceCheckTimestamp(value: string): string {
  return new Intl.DateTimeFormat('en-US', { timeZone: 'America/Los_Angeles', year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' }).format(new Date(value))
}
