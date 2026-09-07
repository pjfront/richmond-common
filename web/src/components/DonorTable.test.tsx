import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import DonorTable from './DonorTable'
import {
  aggregateDonorRecords, availableContributionYears, contributionDateRange,
  contributionsInYear, contributionYear, donorRecordSources, searchDonorRecords, sumRecordedAmounts,
} from '@/lib/historical-donor-records'
import type { DonorContribution } from '@/lib/types'

// Exact public date/amount pairs behind the incorrectly labeled $710.
// Donor labels and employers below are synthetic; no personal data is copied.
const pairs: [string, number][] = [
  ['2024-11-09', 50], ['2024-11-13', 100], ['2024-12-05', 25], ['2024-12-09', 50],
  ['2025-01-05', 335], ['2025-01-09', 50], ['2025-02-09', 50], ['2025-03-09', 50],
]
function record(date: string, amount: number, name = 'Example donor', employer: string | null = null): DonorContribution {
  return { contribution_date: date, amount, donor_name: name, donor_employer: employer, donor_pattern: null, source: 'netfile' }
}
const historical = pairs.map(([date, amount], i) => record(date, amount, `Example donor ${i + 1}`, i === 4 ? 'Example workplace' : null))
const amount = (records: DonorContribution[]) => records.reduce((sum, row) => sum + row.amount, 0)

describe('historical contribution years', () => {
  it('splits the eight retained records into their actual 2024 and 2025 years', () => {
    expect(availableContributionYears(historical)).toEqual(['2025', '2024'])
    expect(contributionsInYear(historical, '2024')).toHaveLength(4)
    expect(amount(contributionsInYear(historical, '2024'))).toBe(225)
    expect(contributionsInYear(historical, '2025')).toHaveLength(4)
    expect(amount(contributionsInYear(historical, '2025'))).toBe(485)
    expect(amount(contributionsInYear(historical, 'all'))).toBe(710)
    expect(contributionsInYear(historical, '2026')).toEqual([])
  })

  it('uses January and December boundaries, preserving signed records and cents', () => {
    const records = [record('2023-12-31', 1), record('2024-01-01', 25.25), record('2024-12-31', -5.25), record('2025-01-01', 3)]
    const selected = contributionsInYear(records, '2024')
    expect(selected.map(row => row.contribution_date)).toEqual(['2024-01-01', '2024-12-31'])
    expect(aggregateDonorRecords(selected)).toMatchObject([{ total_amount: 20, contribution_count: 2 }])
    expect(contributionDateRange(selected)).toEqual({ first: '2024-01-01', last: '2024-12-31' })
  })

  it('adds integer cents across repeated donors and source groups without floating-point drift', () => {
    expect(sumRecordedAmounts([0.1, 0.2])).toBe(0.3)
    expect(sumRecordedAmounts([0.3, -0.1])).toBe(0.2)
    const rows = Array.from({ length: 100 }, () => record('2025-01-01', 0.1))
    expect(aggregateDonorRecords(rows)[0].total_amount).toBe(10)
    expect(donorRecordSources(rows)[0].recordedAmount).toBe(10)
    expect(() => sumRecordedAmounts([Number.NaN])).toThrow('Invalid historical contribution amount')
  })

  it('does not manufacture a year for invalid dates or drop undated records from All records', () => {
    expect(contributionYear('2024-02-30')).toBeNull()
    expect(contributionYear('2024-02-29')).toBe('2024')
    const unknown = [record('', 50)]
    expect(availableContributionYears(unknown)).toEqual([])
    expect(contributionsInYear(unknown, 'all')).toEqual(unknown)
    expect(contributionDateRange(unknown)).toBeNull()
  })

  it('searches donor names and employers without changing the selected record year', () => {
    const donors = aggregateDonorRecords(contributionsInYear(historical, '2025'))
    expect(searchDonorRecords(donors, '  WORKPLACE  ')).toMatchObject([{ donor_name: 'Example donor 5', total_amount: 335, contribution_count: 1 }])
    expect(searchDonorRecords(donors, 'DONOR 6')).toMatchObject([{ total_amount: 50 }])
    expect(searchDonorRecords(donors, 'donor 1')).toEqual([])
    expect(searchDonorRecords(donors, 'missing')).toEqual([])
    expect(searchDonorRecords(donors, '   ')).toEqual(donors)
    expect(searchDonorRecords([], 'anything')).toEqual([])
  })

  it('keeps the recipient committee and exact filing with the selected dated records', () => {
    const rows = historical.map(row => ({ ...row, committee_name: 'Example 2024 council committee', committee_fppc_id: '1467767', filing_id: '217000001', source_url: 'https://netfile.com/Connect2/api/public/image/217000001', contribution_type: 'monetary' }))
    expect(donorRecordSources(contributionsInYear(rows, '2025'))).toMatchObject([{
      committeeName: 'Example 2024 council committee', committeeFppcId: '1467767',
      filingId: '217000001', sourceUrl: 'https://netfile.com/Connect2/api/public/image/217000001',
      recordCount: 4, recordedAmount: 485, dateRange: { first: '2025-01-05', last: '2025-03-09' }, recordTypes: ['monetary'],
    }])
    const unsafe = { ...rows[0], source_url: 'https://example.test/unverified' }
    expect(donorRecordSources([unsafe])[0].sourceUrl).toBeNull()
    expect(donorRecordSources([{ ...unsafe, filing_id: 'not-a-filing' }])[0].filingId).toBeNull()
  })
})

describe('historical donor table', () => {
  it('renders each record year once, defaults to the latest, and never labels these records as the 2026 election', () => {
    const html = renderToStaticMarkup(<DonorTable contributions={historical} />)
    expect(html.match(/>2024<\/button>/g)).toHaveLength(1)
    expect(html.match(/>2025<\/button>/g)).toHaveLength(1)
    expect(html.match(/aria-pressed="true"/g)).toHaveLength(1)
    expect(html).toContain('All records')
    expect(html).toContain('donation records · 2025')
    expect(html).toContain('$485')
    expect(html).toContain('in 4 donation records')
    expect(html).toContain('Jan 5, 2025')
    expect(html).toContain('Mar 9, 2025')
    expect(html).not.toContain('2026')
    expect(html).not.toContain('Election')
    expect(html).not.toContain('$710')
    expect(html).not.toContain('<svg')
  })

  it('keeps record scope and keyboard-accessible filter, search and sorting controls visible', () => {
    const html = renderToStaticMarkup(<DonorTable contributions={historical} />)
    expect(html).toContain('Years refer to donation dates')
    expect(html).toContain('Amount')
    expect(html).toContain('aria-label="Contribution year"')
    expect(html).toMatch(/<label[^>]+for="([^"]+)"[^>]*>Search donors or employers<\/label>/)
    expect(html).toContain('type="search"')
    expect(html).toContain('aria-sort="descending"')
    expect(html).toMatch(/<button type="button"[^>]*>Amount/)
    expect(html).toContain('<caption')
    expect(html).toContain('View all filings on NetFile')
    expect(html).toContain('min-h-11')
    const labeled = renderToStaticMarkup(<DonorTable contributions={[{ ...historical[0], donor_pattern: 'grassroots' }]} />)
    expect(labeled).not.toContain('Grassroots')
    expect(labeled).not.toContain('role="tooltip"')
  })

  it('keeps an empty archive distinct from a zero fundraising total', () => {
    const html = renderToStaticMarkup(<DonorTable contributions={[]} />)
    expect(html).toContain('No historical donation records available.')
    expect(html).not.toContain('$0')
    expect(html).not.toContain('<table')
  })

  it('displays source committee identity and dates without relabeling the recipient as a mayor campaign', () => {
    const rows = historical.map(row => ({ ...row, committee_name: 'Example 2024 council committee', committee_fppc_id: '1467767', filing_id: '217000001', source_url: 'https://netfile.com/Connect2/api/public/image/217000001' }))
    const html = renderToStaticMarkup(<DonorTable contributions={rows} />)
    expect(html).toContain('Committees and source reports for these records (1)')
    expect(html).toContain('Example 2024 council committee')
    expect(html).toContain('FPPC 1467767')
    expect(html).toContain('Original filing 217000001')
    expect(html).toContain('href="https://netfile.com/Connect2/api/public/image/217000001"')
    expect(html).toContain('4 donation records · $485 recorded')
    expect(html).not.toContain('2026')
  })

  it('preserves displayed cents and provides access to donor rows beyond the initial ten', () => {
    const many = Array.from({ length: 12 }, (_, i) => record('2025-01-01', 25.25, `Donor ${i}`))
    const html = renderToStaticMarkup(<DonorTable contributions={many} />)
    expect(html).toContain('$303')
    expect(html).toContain('$25.25')
    expect(html).toContain('Show all 12 donor rows')
    expect(html.match(/<tr /g)).toHaveLength(11) // One header and ten donor rows.
  })
})
