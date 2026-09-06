import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { FinanceEvent, PublicFinanceSnapshot } from '@/lib/queries/finance-public'
import { VERIFIED_ANDERSON_FILINGS } from '@/data/anderson-paper-filings'

const mocks = vi.hoisted(() => ({ snapshot: vi.fn() }))
vi.mock('next/cache', () => ({ unstable_cache: (fn: unknown) => fn }))
vi.mock('@/lib/queries/finance-public', async importOriginal => ({
  ...await importOriginal<typeof import('@/lib/queries/finance-public')>(),
  getPublicFinanceSnapshot: mocks.snapshot,
}))
vi.mock('@/components/PublishedCivicBriefs', () => ({ default: () => null }))
vi.mock('@/components/SubscribeForm', () => ({ default: () => null }))
vi.mock('@/components/SuggestCorrectionLink', () => ({ default: () => null }))
vi.mock('@/lib/queries/candidate-filing-coverage', () => ({ getAndersonFilingCoverage: async () => VERIFIED_ANDERSON_FILINGS }))

import NovemberElection from './NovemberElection'
import MoneyLedger from '@/app/elections/2026-general/money/page'

const event = (overrides: Partial<FinanceEvent> = {}): FinanceEvent => ({
  event_key: 'receipt', scope_key: '0660620:calendar-2026', event_kind: 'receipt',
  donor_name: 'Example donor', donor_fppc_id: null, recipient_name: 'Example committee', recipient_fppc_id: '1488504',
  reporting_filer_name: 'Example committee', reporting_filer_fppc_id: '1488504',
  amount: 100.25, amount_kind: 'monetary', activity_date: '2026-09-01', support_oppose: null,
  candidate_name: null, measure_name: null, election_date: null,
  filing_ids: ['111', '999'], source_urls: ['https://netfile.com/filing/999', 'https://netfile.com/filing/111'],
  source_url: 'https://netfile.com/filing/999', extracted_at: '2026-09-06T12:00:00Z', source_tier: 1,
  reconciliation_status: 'matched_exact', ...overrides,
})
const snapshot = (events: FinanceEvent[], truncated = false): PublicFinanceSnapshot => ({
  events, truncated, coverage: [{
    source: 'NetFile', form_type: '460', scope_key: '0660620:calendar-2026', status: 'partial',
    checked_at: '2026-09-06T12:00:00Z', activity_from: '2026-01-01', activity_through: '2026-09-06',
    filing_count: 2, assertion_count: 2, pending_count: 0, limitations: ['Paper filings may be absent.'], source_url: 'https://netfile.com/search',
  }],
})

describe('resident campaign money presentation', () => {
  beforeEach(() => { mocks.snapshot.mockReset() })

  it('shows gross receipts, signed corrections, and net receipts with cents and distinct meanings', async () => {
    mocks.snapshot.mockResolvedValue(snapshot([event(), event({ event_key: 'adjustment', amount: -25.10, amount_kind: 'negative_adjustment' })]))
    const html = renderToStaticMarkup(await NovemberElection())
    expect(html).toMatch(/Gross cash receipts indexed · 2026<\/dt><dd[^>]*>\$100\.25/)
    expect(html).toMatch(/Signed adjustments to receipts<\/dt><dd[^>]*>-\$25\.10/)
    expect(html).toMatch(/Net reported receipts indexed · 2026<\/dt><dd[^>]*>\$75\.15/)
    expect(html).toContain('Signed adjustment to cash receipts')
    expect(html).toContain('this record alone does not establish a cash refund')
    expect(html).not.toContain('Cash gifts')
  })

  it('withholds limited ledger subtotals while retaining separately verified campaign reports', async () => {
    mocks.snapshot.mockResolvedValue(snapshot([event(), event({
      event_key: 'ie-support', event_kind: 'independent_expenditure', candidate_name: 'Ahmad Anderson',
      election_date: '2026-11-03', support_oppose: 'S', amount: 50,
    }), event({
      event_key: 'ie-opposition', event_kind: 'independent_expenditure', candidate_name: 'Ahmad Anderson',
      election_date: '2026-11-03', support_oppose: 'O', amount: 75,
    })], true))
    const html = renderToStaticMarkup(await NovemberElection())
    expect(html.match(/Subtotal withheld \(record limit\)/g)).toHaveLength(7)
    expect(html).toContain('$54,303')
    expect(html).not.toContain('No published matching records')
    expect(html).toContain('Recent indexed activity (3)')
  })

  it('labels unlike recent values and does not pair sorted filing IDs with an unrelated source URL', async () => {
    mocks.snapshot.mockResolvedValue(snapshot([
      event({ event_key: 'loan', event_kind: 'loan', amount_kind: 'reported_loan_value' }),
      event({ event_key: 'noncash', event_kind: 'noncash', amount_kind: 'noncash_value' }),
      event({ event_key: 'transfer', event_kind: 'transfer' }),
    ]))
    const html = renderToStaticMarkup(await NovemberElection())
    for (const label of ['Reported loan value', 'Reported noncash value', 'Contribution reported made', 'may describe a balance or activity']) expect(html).toContain(label)
    expect(html).toMatch(/href="https:\/\/netfile.com\/filing\/999"[^>]*>Read source filing<\/a>/)
    expect(html).not.toContain('Filing 111')
    expect(html).toContain('activity window searched from Jan 1, 2026 through Sep 6, 2026')
    expect(html).not.toContain('reported activity through')
  })

  it('shows the published search cutoff and unpaired source documents in the ledger', async () => {
    mocks.snapshot.mockResolvedValue(snapshot([event({ amount: -25.10, amount_kind: 'negative_adjustment' })]))
    const html = renderToStaticMarkup(await MoneyLedger({ searchParams: Promise.resolve({}) }))
    expect(html).toContain('Published activity windows searched: from Jan 1, 2026 through Sep 6, 2026')
    expect(html).not.toContain('through election day')
    expect(html).toContain('not the period covered by every filing')
    expect(html).toContain('Reported filing IDs: 111, 999')
    expect(html).toMatch(/href="https:\/\/netfile.com\/filing\/999"[^>]*>Source document 1<\/a>/)
    expect(html).toMatch(/href="https:\/\/netfile.com\/filing\/111"[^>]*>Source document 2<\/a>/)
    expect(html).toContain('Signed adjustment to cash receipts')
    expect(html).toContain('does not by itself establish a cash refund')
  })

  it('replaces Anderson missing subtotals with source-checked period totals and a useful money detail page', async () => {
    mocks.snapshot.mockResolvedValue(snapshot([]))
    const html = renderToStaticMarkup(await NovemberElection())
    expect(html).toContain('$54,303')
    expect(html).toContain('$13,423')
    expect(html).toContain('Cash donations reported · Jan 1–Jun 30, 2026')
    expect(html).not.toContain('Paper reports not indexed')
    expect(html).toContain('FPPC 1481105')
    for (const filing of ['217352920', '217332630']) {
      expect(html).toContain(`https://netfile.com/Connect2/api/public/image/${filing}`)
    }
    expect(html).toContain('Thomas K. Butt')
    expect(html).toContain('Davillier Sloan Inc')
    expect(html).toContain('/elections/2026-general/money/ahmad-anderson')
    expect(html).not.toContain('73,300')
    expect(html.match(/Anderson campaign finances/g)).toHaveLength(1)
  })

  it('keeps original paper filing sources visible when the electronic ledger query fails', async () => {
    mocks.snapshot.mockRejectedValue(new Error('unavailable'))
    const log = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      const html = renderToStaticMarkup(await NovemberElection())
      expect(html).toContain('Campaign records are temporarily unavailable')
      expect(html).toContain('$54,303')
      expect(html).toContain('Anderson campaign finances')
    } finally { log.mockRestore() }
  })
})
