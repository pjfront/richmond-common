import { describe, expect, it } from 'vitest'
import { reportedCents } from './reported-money'
import { JIMENEZ_FINANCE as data, jimenezPeriodTotal, jimenezDonationPeriods, jimenezSourcePage } from './jimenez-finance'

// SHA256 of the independently retained original PDF bytes, September 6, 2026.
const originalHashes: Record<string, string> = {
  '217136864': 'bd4790094966461e3f0fcaf3eda5533efd6979429b3cb87ca069188007cf577f',
  '217270674': '9e9dedcfc00bdab664ae2a90eceff780e69126d45d4164305dfc31ae0946d934',
  '217136849': '2b0c560c8bc8c3ef41ea1e3237f88b3b3c4548b144e43f57bc9094bc47d63b0e',
  '217136825': '2d89c941cc3f0d586b8e3e7d8a26fb8dc7414a0049c1b1d3ab462e42b88b10ed',
  '217136812': '974a7135146cef2944cdbf6b274f03ba64419004d0203c7b22b9da971442c691',
  '216846232': 'ef727c3eb5956fe495b3c3430a10822bfdb37de6457c4ef612c7f63a08ec708c',
  '216835110': 'cc375cb95bcf03dc00654b973b6d5948530efe0332c28f2e44d4582299f20177',
  '216815171': '55041c7e698b29111d8d122a2efc4a727762943dcf50c26c8b25e713ef9e968a',
  '216668328': '394242c34e778d67ed709e95e7d626a43ae153cc0982f2f4c6ea050753d7db70',
}

describe('Jimenez reviewed financial sources', () => {
  it('keeps exact official identity and original hashes without private address fields', () => {
    expect(data.identity).toEqual({ official_id: 'd3438cde-8e34-4bcc-ac0f-56857a18b2f5', committee_id: '67296c98-1b35-4bf8-9cd6-81f797c12e09' })
    expect(data.committee.fppc_id).toBe('1488504')
    expect(data.sources).toHaveLength(9)
    for (const source of data.sources) {
      expect(source.pdf_sha256).toBe(originalHashes[source.filing_id])
      expect(source.metadata_sha256).toMatch(/^[a-f0-9]{64}$/)
      expect(source.source_url).toBe(`https://netfile.com/Connect2/api/public/image/${source.filing_id}`)
      expect(source.agency).toBe('RICH')
      expect(source.committee_fppc_id).toBe('1488504')
    }
    expect(JSON.stringify(data)).not.toMatch(/street_address|phone_number|raw_payload|email_address/)
  })

  it('reconciles three periods to the reported cash total without adding overlapping paper or noncash amounts', () => {
    expect(jimenezPeriodTotal()).toBe(6_036_500)
    expect(data.periodic_history.map(row => row.filing_id)).toEqual(['216815171', '216835110', '217136864'])
    expect(data.periodic_history.reduce((sum, row) => sum + reportedCents(row.itemized_monetary), 0)).toBe(5_891_800)
    expect(data.periodic_history.reduce((sum, row) => sum + reportedCents(row.unitemized_monetary), 0)).toBe(144_700)
    expect(data.periodic.reported.cumulative_noncash).toBe('2000.00')
    expect(data.overlapping_report.filing_id).toBe('216846232')
    expect(data.sources.find(source => source.filing_id === '216846232')?.amended_by_filing_id).toBeNull()
  })

  it('rejects missing, repeated, reordered and internally inconsistent periods', () => {
    expect(() => jimenezPeriodTotal(data.periodic_history.slice(1))).toThrow('gap')
    expect(() => jimenezPeriodTotal([...data.periodic_history, data.periodic_history[2]])).toThrow('overlap')
    expect(() => jimenezPeriodTotal([...data.periodic_history].reverse())).toThrow('gap')
    expect(() => jimenezPeriodTotal(data.periodic_history.slice(0, 2))).toThrow('Latest')
    const altered = structuredClone(data.periodic_history)
    altered[2].monetary_received = '10866.00'
    expect(() => jimenezPeriodTotal(altered)).toThrow('does not reconcile')
    altered[2].itemized_monetary = '10761.00'
    altered[2].ending_cash = '18656.12'
    expect(() => jimenezPeriodTotal(altered)).toThrow('differs from the reported')
  })

  it('retains dated balances and explicit reported zeros', () => {
    const latest = data.periodic.reported
    expect(reportedCents(latest.beginning_cash) + reportedCents(latest.monetary_received) - reportedCents(latest.payments)).toBe(1_865_512)
    expect(latest.ending_cash).toBe('18655.12')
    expect(latest.loans_received).toBe('0.00')
    expect(latest.outstanding_debts).toBe('0.00')
    expect(data.periodic_history.reduce((sum, row) => sum + reportedCents(row.cash_payments), 0)).toBe(4_170_988)
  })

  it('groups five July receipts by received date, preserving the two entries sharing a donor and source', () => {
    const { later, earlier } = jimenezDonationPeriods()
    expect(later).toHaveLength(5)
    expect(new Set(later.map(row => `${row.filing_id}:${row.source_row}`)).size).toBe(5)
    expect(later.reduce((sum, row) => sum + reportedCents(row.amount), 0)).toBe(600_000)
    expect(later.filter(row => row.donor_name === 'Marilyn Langlois').map(row => [row.received_date, row.amount])).toEqual([
      ['2026-07-29', '900.00'], ['2026-07-31', '600.00'],
    ])
    expect(earlier).toHaveLength(1)
    expect(earlier[0]).toMatchObject({ filing_id: '217270674', donor_name: 'Martha Gruelle', received_date: '2026-02-26', amount: '2000.00' })
  })

  it('keeps the matched noncash disclosure out of the rapid cash list and links both originals', () => {
    expect(data.noncash_contribution).toMatchObject({ donor_name: 'Diana Wear', amount: '2000.00', received_date: '2026-04-08', page: 16 })
    expect(data.rapid_receipts.some(row => row.filing_id === '216668328')).toBe(false)
    expect(jimenezSourcePage('216815171', 16)).toBe('https://netfile.com/Connect2/api/public/image/216815171#page=16')
    expect(jimenezSourcePage('216668328', 1)).toBe('https://netfile.com/Connect2/api/public/image/216668328#page=1')
    expect(() => jimenezSourcePage('216815171', 99)).toThrow('not been reviewed')
    expect(() => jimenezSourcePage('unknown', 1)).toThrow('missing')
  })
})
