import { describe, expect, it, vi } from 'vitest'
vi.mock('next/cache', () => ({ unstable_cache: (fn: unknown) => fn }))
import { candidateMoney, type FinanceEvent } from './queries/finance-public'
import { filterFinanceEvents, financeCsv, financeEventLabel } from './finance-ledger'
import { electionCalendar, NOVEMBER_DATES } from './november-election'

const event = (overrides: Partial<FinanceEvent> = {}): FinanceEvent => ({
  event_key: 'one', scope_key: '0660620:calendar-2026', event_kind: 'receipt', donor_name: 'Example donor', donor_fppc_id: null,
  recipient_name: 'Example committee', recipient_fppc_id: '1481105', reporting_filer_name: 'Example committee',
  reporting_filer_fppc_id: '1481105', amount: 100, amount_kind: 'monetary', activity_date: '2026-09-01', support_oppose: null,
  candidate_name: null, measure_name: null, election_date: null, filing_ids: ['123'], source_urls: ['https://netfile.com/example'],
  source_url: 'https://netfile.com/example', extracted_at: '2026-09-06T12:00:00Z', source_tier: 1,
  reconciliation_status: 'source_reported', ...overrides,
})

describe('public money meanings', () => {
  it('keeps gifts, loans, transfers, and election-specific support separate', () => {
    const rows = [event(), event({ event_key: 'loan', event_kind: 'loan', amount: 500 }),
      event({ event_key: 'transfer', event_kind: 'transfer', amount: 300 }),
      event({ event_key: 'ie', event_kind: 'independent_expenditure', candidate_name: 'Ahmad Anderson', election_date: '2026-11-03', support_oppose: 'S', amount: 50 }),
      event({ event_key: 'june', event_kind: 'independent_expenditure', candidate_name: 'Ahmad Anderson', election_date: null, support_oppose: 'S', amount: 900 }),
      event({ event_key: 'other', recipient_fppc_id: '1488504', amount: 200 })]
    const result = candidateMoney(rows, '1481105', 'Ahmad Anderson')
    expect(result.grossReceiptsTotal).toBe(100)
    expect(result.netReceiptsTotal).toBe(100)
    expect(result.supportTotal).toBe(50)
    expect(result.opposition).toHaveLength(0)
  })
  it('does not attribute an expenditure using a surname match', () => {
    const rows = [event({ event_kind: 'independent_expenditure', candidate_name: 'A different Anderson', election_date: '2026-11-03', support_oppose: 'S' })]
    expect(candidateMoney(rows, '1481105', 'Ahmad Anderson').outside).toHaveLength(0)
  })
  it('follows exact committee IDs across both ends and reported spender', () => {
    const rows = [event({ recipient_fppc_id: '12', donor_fppc_id: '951606' }), event({ event_key: 'two' })]
    expect(filterFinanceEvents(rows, '', '951606')).toHaveLength(1)
    expect(filterFinanceEvents(rows, 'no match', '')).toHaveLength(0)
  })
  it('separates signed corrections from gross receipts without inferring a refund', () => {
    const rows = [event({ amount: 100.25 }),
      event({ event_key: 'correction', amount: -25.10, amount_kind: 'negative_adjustment' }),
      event({ event_key: 'increase', amount: 5.20, amount_kind: 'positive_adjustment' }),
      event({ event_key: 'loan', event_kind: 'loan', amount: 500 }),
      event({ event_key: 'noncash', event_kind: 'noncash', amount: 200 }),
      event({ event_key: 'refund', event_kind: 'refund', amount: 30 })]
    const result = candidateMoney(rows, '1481105', 'Ahmad Anderson')
    expect(result.grossReceiptsTotal).toBe(100.25)
    expect(result.receiptAdjustmentsTotal).toBe(-19.90)
    expect(result.netReceiptsTotal).toBe(80.35)
    expect(result.receiptAdjustments).toHaveLength(2)
    expect(financeEventLabel(rows[1])).toBe('Signed adjustment to cash receipts')
  })
  it.each([
    ['receipt', 'Cash contribution reported received'],
    ['transfer', 'Contribution reported made'],
    ['loan', 'Reported loan value'],
    ['noncash', 'Reported noncash value'],
    ['refund', 'Reported refund'],
    ['independent_expenditure', 'Independent expenditure'],
  ] as const)('labels %s without turning unlike amounts into cash gifts', (event_kind, label) => {
    expect(financeEventLabel(event({ event_kind }))).toBe(label)
  })
  it('treats a negative reported amount as an adjustment even if its kind is generic', () => {
    const negative = event({ amount: -10 })
    expect(financeEventLabel(negative)).toBe('Signed adjustment to cash receipts')
    expect(candidateMoney([negative], '1481105', 'Ahmad Anderson').grossReceiptsTotal).toBe(0)
  })
  it('exports adjustment semantics and all source links, neutralizes formulas, and preserves signed numbers', () => {
    const csv = financeCsv([event({ donor_name: '=HYPERLINK("bad")', amount: -50, amount_kind: 'negative_adjustment', source_urls: ['https://netfile.com/example', 'https://netfile.com/other'] })])
    expect(csv).toContain('"\'=HYPERLINK(""bad"")"')
    expect(csv).toContain('"-50"')
    expect(csv).toContain('https://netfile.com/example')
    expect(csv).toContain('"https://netfile.com/example; https://netfile.com/other"')
    expect(csv.split('\r\n')[0].split(',')).toEqual(expect.arrayContaining(['scope_key', 'amount_kind', 'source_urls']))
    expect(csv).toContain('"negative_adjustment"')
    expect(csv).not.toContain('donor_address')
  })
})

describe('November calendar', () => {
  it('keeps disclosure due dates distinct from their coverage end dates', () => {
    expect(NOVEMBER_DATES.find(row => row.date === '2026-09-24')?.detail).toContain('September 19')
    expect(NOVEMBER_DATES.find(row => row.date === '2026-10-22')?.detail).toContain('October 17')
    expect(NOVEMBER_DATES.find(row => row.date === '2026-10-19')?.detail).toContain('November 3')
  })
  it('exports whole-day dates with exclusive ends and valid UTF-8 line folding', () => {
    const calendar = electionCalendar()
    expect(calendar).toContain('DTSTART;VALUE=DATE:20261103\r\nDTEND;VALUE=DATE:20261104')
    expect(calendar.split('\r\n').every(line => Buffer.byteLength(line, 'utf8') <= 75)).toBe(true)
    expect(calendar.match(/BEGIN:VEVENT/g)).toHaveLength(5)
  })
})
