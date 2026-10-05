import { describe, expect, it } from 'vitest'
import { basicSourceScope, basicSourceStatus, type CoreProjectionStatusRow } from './basic-source-status'

const now = Date.parse('2026-10-05T03:30:00Z')
const row: CoreProjectionStatusRow = { feature: 'agenda_refresh', status: 'checked', checked_at: '2026-10-05T03:00:00+00:00', source_scope: 'past-60/next-14-day window' }

describe('bounded source check interpretation', () => {
  it('uses only the recorded check and scope, without deriving completeness', () => {
    const status = basicSourceStatus([row, { ...row, feature: 'finance', status: 'partial', source_scope: '0660620:calendar-2026' }], now)
    expect(status.agenda_refresh).toEqual({ feature: 'agenda_refresh', state: 'checked', checkedAt: '2026-10-05T03:00:00.000Z', scope: 'past-60/next-14-day window' })
    expect(status.finance.state).toBe('partial')
    expect(basicSourceScope(status.agenda_refresh)).toContain('some agendas may be missing')
    expect(basicSourceScope(status.finance)).toContain('Partial electronic index')
  })
  it('keeps rollover pending review distinct from a successful finance refresh', () => {
    const status = basicSourceStatus([{ ...row, feature: 'finance', status: 'pending_review', checked_at: '2026-09-01T12:00:00Z', source_scope: '0660620:calendar-2026' }], now)
    expect(status.finance.state).toBe('pending_review')
    expect(status.finance.checkedAt).toBe('2026-09-01T12:00:00.000Z')
  })
  it('distinguishes a missing source check from an unavailable metadata read', () => {
    expect(basicSourceStatus([], now).finance.state).toBe('never_checked')
    expect(basicSourceStatus([{ ...row, checked_at: null }], now).agenda_refresh.state).toBe('never_checked')
    expect(basicSourceStatus(null, now).agenda_refresh.state).toBe('unavailable')
  })
  it.each(['not-a-time', '2027-10-05T03:00:00Z'])('never calls an invalid or future timestamp a successful check: %s', checked_at => {
    expect(basicSourceStatus([{ ...row, checked_at }], now).agenda_refresh.state).toBe('unavailable')
  })
  it.each(['complete', 'unknown', 'not_indexed'])('does not turn unsupported finance status %s into current coverage', status => {
    expect(basicSourceStatus([{ ...row, feature: 'finance', status }], now).finance.state).toBe('unavailable')
  })
  it('withholds ambiguous identities and avoids inventing an unknown source window', () => {
    expect(basicSourceStatus([row, row], now).agenda_refresh.state).toBe('unavailable')
    const status = basicSourceStatus([{ ...row, source_scope: 'all meetings ever' }], now)
    expect(basicSourceScope(status.agenda_refresh)).toBe('The checked source window is not established.')
  })
})
