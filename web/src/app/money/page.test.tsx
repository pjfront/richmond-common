import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { FinanceEvent, PublicFinanceSnapshot } from '@/lib/queries/finance-public'

const { snapshotRead } = vi.hoisted(() => ({ snapshotRead: vi.fn() }))
vi.mock('@/lib/queries/finance-public', () => ({ getPublicFinanceSnapshot: snapshotRead }))

import MoneyPage from './page'

function event(key: string): FinanceEvent {
  return {
    event_key: key, scope_key: '0660620:calendar-2026', event_kind: 'receipt',
    donor_name: `Contributor ${key}`, donor_fppc_id: null,
    recipient_name: 'Example committee', recipient_fppc_id: '1234567',
    reporting_filer_name: 'Example committee', reporting_filer_fppc_id: '1234567',
    amount: 125, amount_kind: 'cash_receipt', activity_date: '2026-09-01',
    support_oppose: null, candidate_name: null, measure_name: null, election_date: null,
    filing_ids: ['source-1'], source_urls: ['https://example.org/official-filing'],
    source_url: 'https://example.org/official-filing', extracted_at: '2026-09-03T12:00:00Z',
    source_tier: 1, reconciliation_status: 'source_reported',
  }
}

function snapshot(events: FinanceEvent[], truncated = false): PublicFinanceSnapshot {
  return { events, coverage: [], truncated }
}

beforeEach(() => { snapshotRead.mockReset() })

describe('private campaign money record view', () => {
  it('opens the page containing an exact linked record rather than leaving it off the first page', async () => {
    snapshotRead.mockResolvedValue(snapshot(Array.from({ length: 30 }, (_, index) => event(`event-${index}`))))
    const html = renderToStaticMarkup(await MoneyPage({ searchParams: Promise.resolve({ event: 'event-29' }) }))
    expect(html).toContain('page 2 of 2')
    expect(html).toContain('id="event-29"')
    expect(html).not.toContain('id="event-0"')
    expect(html).toContain('href="https://example.org/official-filing"')
    expect(html).toContain('reported 2026 activity')
  })

  it('keeps a failed source read distinct from a zero-result search', async () => {
    snapshotRead.mockRejectedValue(new Error('Source read failed'))
    const html = renderToStaticMarkup(await MoneyPage({ searchParams: Promise.resolve({ q: 'someone' }) }))
    expect(html).toContain('Campaign records are temporarily unavailable')
    expect(html).not.toContain('No indexed records match')
    expect(html).not.toContain('Download matching records')
  })

  it('does not label an out-of-view linked record as nonexistent', async () => {
    snapshotRead.mockResolvedValue(snapshot([event('current-record')], true))
    const html = renderToStaticMarkup(await MoneyPage({ searchParams: Promise.resolve({ event: 'older-record' }) }))
    expect(html).toContain('The linked record is not present in this view of the current index')
    expect(html).toContain('within the limited result set')
    expect(html).toContain('does not establish that the reported activity did not occur')
  })

  it('retains a signed correction and its source rather than presenting it as a new donation or refund', async () => {
    snapshotRead.mockResolvedValue(snapshot([{ ...event('adjustment'), amount: -25, amount_kind: 'cash_receipt_adjustment' }]))
    const html = renderToStaticMarkup(await MoneyPage({ searchParams: Promise.resolve({}) }))
    expect(html).toContain('Signed adjustment to cash receipts')
    expect(html).toContain('-$25.00')
    expect(html).toContain('does not by itself establish a cash refund')
    expect(html).toContain('Source document 1')
  })
})
