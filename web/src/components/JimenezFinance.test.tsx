import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { JIMENEZ_FINANCE as data, JIMENEZ_MONEY_PATH } from '@/lib/jimenez-finance'
import JimenezFinanceSummary from './JimenezFinanceSummary'
import JimenezMoneyPage from '@/app/elections/2026-general/money/claudia-jimenez/page'

vi.mock('@/components/SuggestCorrectionLink', () => ({ default: () => null }))

describe('source-checked Jimenez finance display', () => {
  it('leads with dated cash, separates noncash and keeps the July disclosures incomplete', () => {
    const html = renderToStaticMarkup(<JimenezFinanceSummary />)
    for (const phrase of ['$60,365', '$18,655.12', '$2,000', '$6,000', 'Jan 1–Jun 30, 2026',
      'separate from the cash donations', 'not provide a complete fundraising total since June']) expect(html).toContain(phrase)
    expect(html).toContain(`href="${JIMENEZ_MONEY_PATH}"`)
    expect(html).toContain('dateTime="2026-09-06"')
    expect(html).not.toMatch(/68,918|\$710|Martha Gruelle|February/)
  })

  it('shows reported summary equations and the distinct February, July and noncash source records', () => {
    const html = renderToStaticMarkup(<JimenezMoneyPage />)
    for (const phrase of ['$60,365', '$18,655.12', '$23,221.14', '$10,865', '$15,431.02', '$41,709.88',
      'May 17–June 30, 2026', 'not its balance today', 'Donations received after June 30 (5)',
      'A February donation reported in August', 'Diana Wear', 'speech coaching', '$1,447',
      'not every individual donation', 'outside', 'AI-written explanation', 'does not establish an additional cash donation']) {
      expect(html.toLowerCase()).toContain(phrase.toLowerCase())
    }
    expect(html).not.toMatch(/68,918|\$710|\$66,365|\$68,365|largest donor|complete donor list/i)
    const july = html.slice(html.indexOf('id="donations"'), html.indexOf('A February donation reported in August'))
    expect(july).not.toContain('Martha Gruelle')
    expect(july.match(/Marilyn Langlois/g)).toHaveLength(2)
    expect(july).toContain('dateTime="2026-07-29"')
    expect(july).toContain('dateTime="2026-07-31"')
    const february = html.slice(html.indexOf('A February donation reported in August'), html.indexOf('id="calculation"'))
    expect(february).toContain('Martha Gruelle')
    expect(february).toContain('dateTime="2026-02-26"')
    expect(february).toContain('dateTime="2026-08-23"')
    for (const row of data.periodic_history) expect(html).toContain(`${row.filing_id}#page=3`)
    for (const row of data.rapid_receipts) expect(html).toContain(`${row.filing_id}#page=1`)
    expect(html).toContain('216815171#page=16')
    expect(html).toContain('216668328#page=1')
    expect(html).toContain('216846232#page=3')
    expect(html).toContain('FPPC 1488504')
  })
})
