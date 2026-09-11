import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { FinanceEvent, PublicFinanceSnapshot } from '@/lib/queries/finance-public'

const mocks = vi.hoisted(() => ({ snapshot: vi.fn() }))
vi.mock('@/lib/queries/finance-public', () => ({ getPublicFinanceSnapshot: mocks.snapshot }))
vi.mock('@/components/SuggestCorrectionLink', () => ({ default: () => <span>Suggest a correction</span> }))
import MoneyLedger from './page'
import { GET } from '@/app/api/finance/export/route'

const event = (overrides: Partial<FinanceEvent> = {}): FinanceEvent => ({
  event_key: 'receipt', scope_key: '0660620:calendar-2026', event_kind: 'receipt', donor_name: 'Named donor', donor_fppc_id: '951606',
  recipient_name: 'Safe Richmond Neighborhoods', recipient_fppc_id: '1490887', reporting_filer_name: 'Safe Richmond Neighborhoods',
  reporting_filer_fppc_id: '1490887', amount: 100, amount_kind: 'monetary', activity_date: '2026-09-08', support_oppose: null,
  candidate_name: null, measure_name: null, election_date: null, filing_ids: ['123'], source_urls: ['https://netfile.com/example'],
  source_url: 'https://netfile.com/example', extracted_at: '2026-09-10T12:00:00Z', source_tier: 1,
  reconciliation_status: 'source_reported', ...overrides,
})
const snapshot = (): PublicFinanceSnapshot => ({
  events: [event(), event({ event_key: 'other-recipient', recipient_fppc_id: '1234567' }),
    event({ event_key: 'spending', event_kind: 'independent_expenditure', candidate_name: 'Ahmad Anderson', recipient_fppc_id: null })],
  coverage: [{ source: 'netfile', form_type: 'S496', scope_key: '0660620:calendar-2026', status: 'partial', checked_at: '2026-09-10T12:00:00Z',
    activity_from: '2026-01-01', activity_through: '2026-09-10', filing_count: 13, assertion_count: 32, pending_count: 2,
    limitations: [], source_url: 'https://public.netfile.com/pub2/?AID=RICH' }], truncated: false,
})

describe('money trail, source context and matching download', () => {
  beforeEach(() => { mocks.snapshot.mockReset(); mocks.snapshot.mockResolvedValue(snapshot()) })

  it('offers checked campaign summaries and source-backed group starting points without a search', async () => {
    const html = renderToStaticMarkup(await MoneyLedger({ searchParams: Promise.resolve({}) }))
    expect(html).toContain('/money/ahmad-anderson')
    expect(html).toContain('/money/claudia-jimenez')
    expect(html).toContain('href="?committee=1490887"')
    expect(html).toContain('href="?committee=1390351"')
    expect(html).toContain('These records are not a spending or fundraising total')
    expect(html).toContain('2 source entries await')
    expect(html).toContain('periodic spending reports are not yet included')
    expect(html).not.toContain('2026 Election')
  })

  it('keeps committee and direction filters in the form, results and CSV', async () => {
    const params = { committee: '1490887', role: 'recipient', activity: 'contributions' }
    const html = renderToStaticMarkup(await MoneyLedger({ searchParams: Promise.resolve(params) }))
    expect(html).toContain('name="committee" value="1490887"')
    expect(html).toContain('1 indexed record')
    expect(html).toContain('/api/finance/export?committee=1490887&amp;activity=contributions&amp;role=recipient')
    expect(html).toContain('Richmond Police Officers Association')
    expect(html).toContain('216859596#page=3')
    expect(html).toContain('A sponsor is a relationship')
    const result = await GET(new Request(`https://richmondcommons.org/api/finance/export?${new URLSearchParams(params)}`))
    expect(result.status).toBe(200)
    const csv = await result.text()
    expect(csv).toContain('"receipt"')
    expect(csv).not.toContain('other-recipient')
    expect(csv).not.toContain('"spending"')
  })

  it('filters spending by reported spender without inventing an election', async () => {
    const params = { committee: '1490887', role: 'source', activity: 'independent_expenditure' }
    const html = renderToStaticMarkup(await MoneyLedger({ searchParams: Promise.resolve(params) }))
    expect(html).toContain('1 indexed record')
    expect(html).toContain('Reported spender:')
    expect(html).toContain('Election not established in this record')
    const csv = await (await GET(new Request(`https://richmondcommons.org/api/finance/export?${new URLSearchParams(params)}`))).text()
    expect(csv).toContain('"spending"')
    expect(csv).not.toContain('"receipt"')
  })

  it('keeps filters across pagination and interprets repeated URL parameters consistently', async () => {
    mocks.snapshot.mockResolvedValue({ ...snapshot(), events: Array.from({ length: 26 }, (_, index) => event({ event_key: `row-${index}` })) })
    const html = renderToStaticMarkup(await MoneyLedger({ searchParams: Promise.resolve({ committee: ['1490887', '1234567'], role: 'recipient', activity: 'contributions' }) }))
    expect(html).toContain('committee=1490887&amp;activity=contributions&amp;role=recipient&amp;page=2#records')
    const csv = await (await GET(new Request('https://richmondcommons.org/api/finance/export?committee=1490887&committee=1234567&role=recipient&activity=contributions'))).text()
    expect(csv.split('\r\n').filter(Boolean)).toHaveLength(27)
  })

  it('shows dated EBWF sponsors with exact source pages, separately from contributors', async () => {
    const html = renderToStaticMarkup(await MoneyLedger({ searchParams: Promise.resolve({ committee: '1390351' }) }))
    expect(html).toContain('ACCE Action')
    expect(html).toContain('APEN Action')
    expect(html).toContain('Service Employees International Union Local 1021')
    expect(html).toContain('217301754#page=3')
    expect(html).toContain('217301754#page=4')
    expect(html).toContain('Aug 27, 2026')
    expect(html).not.toContain('controlled by')
  })

  it('keeps loading failure distinct from no matches and refuses an incomplete CSV', async () => {
    mocks.snapshot.mockRejectedValueOnce(new Error('unavailable'))
    const html = renderToStaticMarkup(await MoneyLedger({ searchParams: Promise.resolve({}) }))
    expect(html).toContain('could not be loaded')
    expect(html).not.toContain('0 indexed')
    expect(html).not.toContain('No indexed records match')
    mocks.snapshot.mockResolvedValue({ ...snapshot(), truncated: true })
    expect((await GET(new Request('https://richmondcommons.org/api/finance/export'))).status).toBe(503)
  })
})
