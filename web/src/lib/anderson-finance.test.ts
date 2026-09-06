import { describe, expect, it } from 'vitest'
import { VERIFIED_ANDERSON_FILINGS } from '@/data/anderson-paper-filings'
import { ANDERSON_FINANCE as data, andersonPeriodTotal, andersonDonationPeriods, andersonSourcePage,
  reportedCents, hasNewAndersonReports, andersonPaymentGroups } from './anderson-finance'

describe('Anderson source-checked report arithmetic', () => {
  it('counts four nonoverlapping 2026 periods once and excludes the 2025 carryover', () => {
    expect(andersonPeriodTotal()).toBe(5_430_300)
    expect(andersonPeriodTotal() + reportedCents(data.prior_year.monetary_received))
      .toBe(reportedCents(data.periodic.reported.cumulative_monetary))
    expect(data.periodic_history[0].same_period_sources).toEqual(['217027183'])
    expect(data.periodic_history).toHaveLength(4)
  })
  it('refuses an omitted, duplicated or reordered period instead of publishing a plausible subtotal', () => {
    expect(() => andersonPeriodTotal(data.periodic_history.slice(1))).toThrow('gap')
    expect(() => andersonPeriodTotal([...data.periodic_history, data.periodic_history[3]])).toThrow('overlap')
    expect(() => andersonPeriodTotal([...data.periodic_history].reverse())).toThrow('gap')
    expect(() => andersonPeriodTotal(data.periodic_history.slice(0, 3))).toThrow('Latest')
  })
  it('groups donations by receipt date, not the much later filing date', () => {
    const { later, earlier } = andersonDonationPeriods()
    expect(later.map(row => row.filing_id)).toEqual(['217352920', '217332630'])
    expect(later.reduce((total, row) => total + reportedCents(row.amount), 0)).toBe(200_000)
    expect(earlier.map(row => row.received_date)).toEqual(['2026-05-16', '2026-05-16'])
  })
  it('preserves blank source fields and the latest cash equation without inventing small-donor totals', () => {
    const report = data.periodic.reported
    expect(reportedCents(report.beginning_cash) + reportedCents(report.monetary_received) - reportedCents(report.payments))
      .toBe(reportedCents(report.ending_cash))
    expect(report.loans_received).toBeNull()
    expect(report.noncash_received).toBeNull()
    expect(report.outstanding_debts).toBeNull()
    expect(data.periodic_history[0].payments).toBeNull()
  })
  it('requires a preserved reviewed source page and fixed decimal amounts', () => {
    expect(andersonSourcePage('217094857', 3)).toBe('https://netfile.com/Connect2/api/public/image/217094857#page=3')
    expect(() => andersonSourcePage('217094857', 99)).toThrow('not been reviewed')
    expect(() => andersonSourcePage('unknown', 1)).toThrow('missing')
    for (const value of ['NaN', '', '10,000.00', '-5.00', '0.001']) expect(() => reportedCents(value)).toThrow()
    for (const source of data.sources) {
      expect(source.pdf_sha256).toMatch(/^[a-f0-9]{64}$/)
      expect(source.metadata_sha256).toMatch(/^[a-f0-9]{64}$/)
      expect(source.source_url).toBe(`https://netfile.com/Connect2/api/public/image/${source.filing_id}`)
    }
  })
  it('groups exact payee names and reconciles the payment attachment to the rounded report amount', () => {
    const payees = andersonPaymentGroups()
    expect(payees).toHaveLength(8)
    expect(payees.slice(0, 2).map(row => [row.name, row.cents])).toEqual([
      ['The Next Generations', 553_560], ['Pacific Print', 521_140],
    ])
    expect(data.payments).toHaveLength(14)
    const paid = payees.reduce((total, row) => total + row.cents, 0)
    expect(paid).toBe(1_261_190)
    expect(Math.round(paid / 100) * 100).toBe(reportedCents(data.periodic.reported.payments))
  })
  it('marks a new source for review without replacing published figures', () => {
    expect(hasNewAndersonReports(VERIFIED_ANDERSON_FILINGS)).toBe(false)
    expect(hasNewAndersonReports({ ...VERIFIED_ANDERSON_FILINGS,
      recentRapid: [{ ...VERIFIED_ANDERSON_FILINGS.recentRapid[0], id: '999999999' }] })).toBe(true)
    expect(hasNewAndersonReports({ ...VERIFIED_ANDERSON_FILINGS,
      latestPeriodic: { ...VERIFIED_ANDERSON_FILINGS.latestPeriodic, id: '999999999' } })).toBe(true)
    expect(andersonPeriodTotal()).toBe(5_430_300)
  })
})
