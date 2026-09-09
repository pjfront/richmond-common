import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import ComplianceStats from './ComplianceStats'
import PublicRecordsClient from './PublicRecordsClient'
import type { NextRequestRequest } from '@/lib/types'
const stats = { totalRequests: 2, closedRequests: 1, notClosedRequests: 1, closureTimingCount: 1, avgClosureDays: 35 }
const request = { id: 'one', request_number: '26-001', status: 'Open', submitted_date: '2026-01-01', department: 'Clerk',
  days_to_close: null, updated_at: '2026-09-06T12:00:00Z', portal_url: 'https://cityofrichmondca.nextrequest.com/requests/26-001' } as NextRequestRequest
it('shows closure duration with denominator and neutral observed status counts', () => {
  const html = renderToStaticMarkup(<ComplianceStats stats={stats} />)
  expect(html).toContain('Average time to closure')
  expect(html).toContain('35 days')
  expect(html).toContain('Not marked closed')
  expect(html).toContain('1 marked-closed records')
  expect(html).not.toMatch(/On-Time|Avg Response|past deadline|Currently Overdue/)
})
it('shows unavailable rather than zero when no usable closure timing exists', () => {
  const html = renderToStaticMarkup(<ComplianceStats stats={{ ...stats, closureTimingCount: 0, avgClosureDays: null }} />)
  expect(html).toContain('Unavailable')
  expect(html).not.toContain('0 days')
})
describe('source-linked public-record views', () => {
  it('does not invent missing request text or deadline breaches for long-open records', () => {
    const html = renderToStaticMarkup(<PublicRecordsClient requests={[request]} stats={stats} />)
    expect(html).toContain('indexed public records requests')
    expect(html).toContain('Request #26-001')
    expect(html).not.toMatch(/since June 2022|No description available|past deadline|10-day|On-Time/)
  })
})
