import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { VERIFIED_ANDERSON_FILINGS } from '@/data/anderson-paper-filings'
import { ANDERSON_FINANCE as data } from '@/lib/anderson-finance'
vi.mock('@/lib/queries/candidate-filing-coverage', () => ({ getAndersonFilingCoverage: async () => VERIFIED_ANDERSON_FILINGS }))
vi.mock('@/components/SuggestCorrectionLink', () => ({ default: () => null }))
import AndersonMoneyPage from '@/app/elections/2026-general/money/ahmad-anderson/page'
import { GET } from '@/app/elections/2026-general/money/ahmad-anderson/reports.csv/route'

describe('readable source-backed Anderson finances', () => {
  it('shows actual figures, period arithmetic, donor receipt dates and source limitations', async () => {
    const html = renderToStaticMarkup(await AndersonMoneyPage())
    expect(html).toContain('$54,303')
    expect(html).toContain('$18,997')
    expect(html).toContain('Why not $73,300?')
    expect(html).toContain('$13,423')
    expect(html).toContain('$5,535.60')
    expect(html).toContain('The Next Generations')
    expect(html).toContain('Read all 14 payments')
    expect(html).toContain('not its balance today')
    expect(html).toContain('May donations reported in August (2)')
    expect(html).toContain('Donations received after June 30 (2)')
    expect(html).toContain('not been fully matched to every individual donation')
    expect(html).toContain('Safe Richmond Neighborhoods is separate')
    expect(html).not.toContain('Paper reports not indexed')
    expect(html).not.toContain('paper filing coverage')
    for (const row of data.periodic_history) expect(html).toContain(`${row.filing_id}#page=3`)
    for (const row of data.rapid_receipts) expect(html).toContain(`${row.filing_id}#page=1`)
  })
  it('exports separate period totals and individual disclosures, with exact source hashes and no combined total', async () => {
    const response = GET()
    expect(response.headers.get('content-type')).toBe('text/csv; charset=utf-8')
    const csv = await response.text()
    expect(csv.trim().split('\r\n')).toHaveLength(23)
    expect(csv.match(/"reported_period_monetary_total"/g)).toHaveLength(4)
    expect(csv.match(/"reported_contribution_disclosure_do_not_add_to_period_totals"/g)).toHaveLength(4)
    expect(csv.match(/"individual_payment_included_in_period_spending"/g)).toHaveLength(14)
    expect(csv).toContain('"2026-05-16","Michael Bush","2500.00"')
    expect(csv).not.toContain('"73300.00"')
    expect(csv).not.toContain('street_address')
    expect(csv).toContain(data.sources[0].pdf_sha256)
  })
})
