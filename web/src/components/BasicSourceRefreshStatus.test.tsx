import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { basicSourceStatus } from '@/lib/basic-source-status'
const { read } = vi.hoisted(() => ({ read: vi.fn() }))
vi.mock('@/lib/queries/basic-source-status', () => ({ getBasicSourceRefreshStatus: read }))
import BasicSourceRefreshStatus, { BasicSourceRefreshStatusView } from './BasicSourceRefreshStatus'

beforeEach(() => read.mockReset())

describe('visible basic source status', () => {
  it('displays attributed check times with partial scope and pending votes/paper figures', () => {
    const status = basicSourceStatus([
      { feature: 'agenda_refresh', status: 'partial', checked_at: '2026-10-04T12:00:00Z', source_scope: 'past-60/next-14-day window' },
      { feature: 'finance', status: 'partial', checked_at: '2026-10-03T12:00:00Z', source_scope: '0660620:calendar-2026' },
    ], Date.parse('2026-10-05T12:00:00Z'))
    const html = renderToStaticMarkup(<BasicSourceRefreshStatusView status={status} />)
    expect(html).toContain('dateTime="2026-10-04T12:00:00.000Z"')
    expect(html).toContain('Source last checked')
    expect(html).toContain('Past 60 days and next 14 days only')
    expect(html).toContain('New votes await review')
    expect(html).toContain('Paper filings await review')
    expect(html).toContain('do not establish complete campaign totals')
    expect(html).toContain('href="https://pub-richmond.escribemeetings.com/"')
  })
  it('keeps a frozen finance index explicit rather than labeling it current', () => {
    const status = basicSourceStatus([{ feature: 'finance', status: 'pending_review', checked_at: '2026-10-03T12:00:00Z', source_scope: '0660620:calendar-2026' }], Date.parse('2027-01-01T12:00:00Z'))
    const html = renderToStaticMarkup(<BasicSourceRefreshStatusView status={status} />)
    expect(html).toContain('saved 2026 index is awaiting review')
    expect(html).not.toContain('up to date')
    expect(html).not.toContain('current figures')
  })
  it('explains never-checked and unavailable states without inventing freshness', () => {
    const never = renderToStaticMarkup(<BasicSourceRefreshStatusView status={basicSourceStatus([])} />)
    const unavailable = renderToStaticMarkup(<BasicSourceRefreshStatusView status={basicSourceStatus(null)} />)
    expect(never).toContain('No source check has been recorded yet')
    expect(unavailable).toContain('Source check time is unavailable')
    expect(never + unavailable).not.toContain('Source last checked')
  })
  it('renders nothing for local or nonbasic editions', async () => {
    read.mockResolvedValue(null)
    expect(await BasicSourceRefreshStatus()).toBeNull()
  })
})
