import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import DonorTable from './DonorTable'
import {
  availableContributionYears, contributionDateRange, contributionsInYear, contributionYear,
  filterHistoricalRecords, historicalFilingUrl, historicalRecordKind, historicalRecordSource,
} from '@/lib/historical-donor-records'
import type { DonorContribution } from '@/lib/types'

const csv = vi.hoisted(() => ({ props: null as null | { rows: Record<string, unknown>[] } }))
vi.mock('@/components/CsvDownloadButton', () => ({ default: (props: { rows: Record<string, unknown>[] }) => {
  csv.props = props
  return <button>Download CSV</button>
} }))

// Exact date/amount pairs behind the incorrect $710 election label. Names are synthetic.
const pairs: [string, number][] = [
  ['2024-11-09', 50], ['2024-11-13', 100], ['2024-12-05', 25], ['2024-12-09', 50],
  ['2025-01-05', 335], ['2025-01-09', 50], ['2025-02-09', 50], ['2025-03-09', 50],
]
function record(date: string, amount: number, name = 'Example name', type = 'monetary'): DonorContribution {
  return { contribution_date: date, amount, donor_name: name, donor_employer: 'Reported workplace', donor_pattern: null,
    contribution_type: type, source: 'netfile', committee_name: 'Example 2024 committee', committee_fppc_id: '1467767',
    filing_id: '214610872', source_url: 'https://netfile.com/Connect2/api/public/image/214610872' }
}
const historical = pairs.map(([date, amount]) => record(date, amount))

describe('historical individual entries', () => {
  it('uses the actual calendar year without implying election attribution', () => {
    expect(availableContributionYears(historical)).toEqual(['2025', '2024'])
    expect(contributionsInYear(historical, '2024')).toHaveLength(4)
    expect(contributionsInYear(historical, '2025')).toHaveLength(4)
    expect(contributionsInYear(historical, '2026')).toEqual([])
    expect(contributionsInYear(historical, 'all')).toEqual(historical)
    expect(contributionDateRange(historical)).toEqual({ first: '2024-11-09', last: '2025-03-09' })
    expect(contributionYear('2024-02-30')).toBeNull()
    expect(contributionYear('2024-02-29')).toBe('2024')
    expect(contributionsInYear([record('', 50)], 'all')).toHaveLength(1)
  })

  it('preserves identical names, repeated report entries, noncash, loans and transfers without merging', () => {
    const entries = [record('2025-01-05', 100), record('2025-01-05', 100), record('2025-01-05', 2000, 'Example name', 'nonmonetary'),
      record('2025-01-05', 300, 'Example name', 'loan'), record('2025-01-05', 3413, 'Own campaign committee', 'transfer'),
      record('2025-01-05', 50, 'Unitemized contributions'), record('2025-01-05', -25, 'Example name')]
    expect(filterHistoricalRecords(entries, 'all', 'all', '')).toEqual(entries)
    expect(filterHistoricalRecords(entries, 'all', 'monetary', '')).toHaveLength(3)
    expect(filterHistoricalRecords(entries, 'all', 'noncash', '')).toEqual([entries[2]])
    expect(filterHistoricalRecords(entries, 'all', 'loan', '')).toEqual([entries[3]])
    expect(filterHistoricalRecords(entries, 'all', 'transfer', '')).toEqual([entries[4]])
    expect(filterHistoricalRecords(entries, 'all', 'adjustment', '')).toEqual([entries[6]])
    expect(historicalRecordKind({ amount: -10, contribution_type: 'nonmonetary' })).toBe('adjustment')
    expect(historicalRecordKind({ amount: 100, contribution_type: 'unexpected' })).toBe('other')
    expect(historicalRecordKind({ amount: 100 })).toBe('other')
    expect(historicalRecordKind({ amount: 100, contribution_type: 'refund' })).toBe('refund')
    expect(historicalRecordKind({ amount: 3413, contribution_type: 'monetary' })).toBe('monetary') // Never infer a transfer from its name.
  })

  it('searches exact record fields without borrowing an employer from another row with the same name', () => {
    const entries = [record('2025-01-05', 100), { ...record('2024-01-05', 200), donor_employer: 'Other workplace' }]
    expect(filterHistoricalRecords(entries, 'all', 'all', '  REPORTED workplace ')).toEqual([entries[0]])
    expect(filterHistoricalRecords(entries, '2025', 'all', 'other workplace')).toEqual([])
    expect(filterHistoricalRecords(entries, 'all', 'all', '1467767')).toEqual(entries)
    expect(filterHistoricalRecords(entries, 'all', 'all', '214610872')).toEqual(entries)
  })

  it('only links a verified local filing source, never a guessed CAL-ACCESS NetFile image', () => {
    expect(historicalFilingUrl('netfile', '214610872')).toBe('https://netfile.com/Connect2/api/public/image/214610872')
    expect(historicalFilingUrl('cal_access', '214610872')).toBeNull()
    expect(historicalFilingUrl(null, '214610872')).toBeNull()
    expect(historicalFilingUrl('netfile', '214610872?foo=bar')).toBeNull()
    expect(historicalRecordSource(historical[0])).toBe(historical[0].source_url)
    expect(historicalRecordSource({ ...historical[0], source_url: 'https://example.test/other' })).toBeNull()
  })
})

describe('historical finance browser', () => {
  it('shows separate dated entries and never calculates $710/$485 or a donor count', () => {
    const html = renderToStaticMarkup(<DonorTable contributions={historical} />)
    expect(html).toContain('Showing 4 of 4 matching entries')
    expect(html).toContain('$335')
    expect(html).toContain('Jan 5, 2025')
    expect(html).toContain('Mar 9, 2025')
    expect(html).toContain('Reported name')
    expect(html).toContain('Reported employer:')
    expect(html).not.toContain('$710')
    expect(html).not.toContain('$485')
    expect(html).not.toContain('2026')
    expect(html).not.toContain('4 donors')
    expect(html).not.toContain('Election')
    expect(csv.props?.rows).toHaveLength(4)
    expect(csv.props?.rows.map(row => row.amount)).toEqual([50, 50, 50, 335])
  })

  it('keeps own-committee transfers and signed entries visible without claiming they are unique donors or net cash', () => {
    const entries = [record('2025-02-01', 3413, 'Own campaign committee', 'transfer'),
      record('2025-02-01', 2000, 'Same reported name', 'nonmonetary'),
      record('2025-02-01', 100, 'Same reported name'), record('2025-02-01', -25.25, 'Same reported name'),
      record('2025-02-01', 100, 'Same reported name')]
    const html = renderToStaticMarkup(<DonorTable contributions={entries} />)
    expect(html).toContain('Showing 5 of 5 matching entries')
    expect(html.match(/>Same reported name<\/span>/g)).toHaveLength(4)
    expect(html).toContain('$3,413')
    expect(html).toContain('-$25.25')
    expect(html).toContain('Recorded as a transfer')
    expect(html).toContain('Recorded as noncash')
    expect(html).toContain('Signed adjustment')
    expect(html).not.toContain('$5,587.75')
    expect(html).not.toContain('5 donors')
    expect(csv.props?.rows).toHaveLength(5)
    expect(csv.props?.rows[3]).toMatchObject({ amount: -25.25, contribution_type: 'monetary' })
  })

  it('exports every matching entry even when only the first twenty are displayed', () => {
    const entries = Array.from({ length: 23 }, (_, i) => record('2025-02-01', i + 1))
    const html = renderToStaticMarkup(<DonorTable contributions={entries} />)
    expect(html).toContain('Showing 20 of 23 matching entries')
    expect(html).toContain('Show 20 more entries')
    expect(csv.props?.rows).toHaveLength(23)
    expect(csv.props?.rows[0]).toMatchObject({ committee_fppc_id: '1467767', source_url: historical[0].source_url })
  })

  it('keeps filter/search/sort/export controls accessible and an empty archive distinct from zero money', () => {
    const html = renderToStaticMarkup(<DonorTable contributions={historical} />)
    expect(html).toContain('Record year')
    expect(html).toContain('Recorded type')
    expect(html).toContain('Sort entries')
    expect(html).toContain('type="search"')
    expect(html).toContain('aria-live="polite"')
    expect(html).toContain('<caption')
    expect(html).toContain('md:table-row')
    expect(html).toContain('min-h-11')
    const empty = renderToStaticMarkup(<DonorTable contributions={[]} />)
    expect(empty).toContain('No historical finance entries available.')
    expect(empty).not.toContain('$0')
    expect(empty).not.toContain('<table')
  })
})
