import data from '@/data/jimenez-reported-finance.json'
import { reportedCents } from '@/lib/reported-money'

export const JIMENEZ_FINANCE = data
export const JIMENEZ_MONEY_PATH = '/elections/2026-general/money/claudia-jimenez'

export function jimenezSource(filingId: string) {
  const source = data.sources.find(item => item.filing_id === filingId)
  if (!source) throw new Error('Reviewed filing source missing')
  return source
}

export function jimenezSourcePage(filingId: string, page: number): string {
  const source = jimenezSource(filingId)
  if (!source.reviewed_pages.includes(page)) throw new Error('Page has not been reviewed')
  return `${source.source_url}#page=${page}`
}

/** Use current amendments once, with no gaps or overlapping reporting periods. */
export function jimenezPeriodTotal(reports = data.periodic_history): number {
  let expectedStart = '2026-01-01'
  let total = 0
  for (const report of reports) {
    const source = jimenezSource(report.filing_id)
    if (source.form !== '460' || source.amended_by_filing_id !== null
      || source.period_start !== expectedStart || !source.period_end
      || source.period_end < expectedStart || !source.period_end.startsWith('2026-')) {
      throw new Error('Reviewed periods have a gap, overlap or superseded source')
    }
    const received = reportedCents(report.monetary_received)
    if (reportedCents(report.itemized_monetary) + reportedCents(report.unitemized_monetary) !== received
      || reportedCents(report.beginning_cash) + received - reportedCents(report.cash_payments)
        !== reportedCents(report.ending_cash)) {
      throw new Error('Reviewed period summary does not reconcile')
    }
    total += received
    expectedStart = new Date(Date.parse(`${source.period_end}T00:00:00Z`) + 86_400_000).toISOString().slice(0, 10)
  }
  if (!reports.length || reports.at(-1)?.filing_id !== data.periodic.filing_id) {
    throw new Error('Latest reviewed period is missing')
  }
  if (total !== reportedCents(data.periodic.reported.cumulative_monetary)) {
    throw new Error('Reviewed period sum differs from the reported calendar-year total')
  }
  return total
}

/** Received dates decide the period; a late filing is not a new donation. */
export function jimenezDonationPeriods() {
  const through = jimenezSource(data.periodic.filing_id).period_end!
  return {
    later: data.rapid_receipts.filter(receipt => receipt.received_date > through),
    earlier: data.rapid_receipts.filter(receipt => receipt.received_date <= through),
  }
}
