import { describe, expect, it, vi } from 'vitest'
vi.mock('next/cache', () => ({ unstable_cache: (fn: unknown) => fn }))
import { candidateMoney, type FinanceEvent } from './queries/finance-public'
import { filterFinanceEvents, financeCsv } from './finance-ledger'
import { electionCalendar, NOVEMBER_DATES } from './november-election'

const event = (overrides: Partial<FinanceEvent> = {}): FinanceEvent => ({
  event_key: 'one', event_kind: 'receipt', donor_name: 'Example donor', donor_fppc_id: null,
  recipient_name: 'Example committee', recipient_fppc_id: '1481105', reporting_filer_name: 'Example committee',
  reporting_filer_fppc_id: '1481105', amount: 100, activity_date: '2026-09-01', support_oppose: null,
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
    expect(result.receiptsTotal).toBe(100)
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
  it('exports source links, neutralizes spreadsheet formulas, and preserves numeric refunds', () => {
    const csv = financeCsv([event({ donor_name: '=HYPERLINK("bad")', amount: -50 })])
    expect(csv).toContain('"\'=HYPERLINK(""bad"")"')
    expect(csv).toContain('"-50"')
    expect(csv).toContain('https://netfile.com/example')
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
