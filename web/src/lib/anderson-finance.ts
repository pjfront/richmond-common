import data from '@/data/anderson-reported-finance.json'
import type { CandidateFilingCoverage } from '@/data/anderson-paper-filings'

export const ANDERSON_FINANCE = data
export const ANDERSON_MONEY_PATH = '/elections/2026-general/money/ahmad-anderson'

/** Fixed decimal dollars become integer cents before addition. No inferred zero. */
export function reportedCents(value: string): number {
  if (!/^\d{1,10}\.\d{2}$/.test(value)) throw new Error('Invalid reviewed financial amount')
  const [dollars, cents] = value.split('.')
  return Number(dollars) * 100 + Number(cents)
}

export function formatReportedMoney(value: string | number): string {
  const cents = typeof value === 'string' ? reportedCents(value) : value
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD',
    minimumFractionDigits: cents % 100 ? 2 : 0, maximumFractionDigits: 2 }).format(cents / 100)
}

export function andersonSource(filingId: string) {
  const source = data.sources.find(item => item.filing_id === filingId)
  if (!source) throw new Error('Reviewed filing source missing')
  return source
}

export function andersonSourcePage(filingId: string, page: number): string {
  const source = andersonSource(filingId)
  if (!source.reviewed_pages.includes(page)) throw new Error('Page has not been reviewed')
  return `${source.source_url}#page=${page}`
}

/** Add one summary per adjacent, nonoverlapping 2026 reporting period. */
export function andersonPeriodTotal(reports = data.periodic_history): number {
  let expectedStart = '2026-01-01'
  let total = 0
  for (const report of reports) {
    const source = andersonSource(report.filing_id)
    if (source.form !== '460' || source.period_start !== expectedStart || !source.period_end
      || source.period_end < expectedStart || !source.period_end.startsWith('2026-')) {
      throw new Error('Reviewed periods have a gap, overlap or different year')
    }
    total += reportedCents(report.monetary_received)
    expectedStart = new Date(Date.parse(`${source.period_end}T00:00:00Z`) + 86_400_000).toISOString().slice(0, 10)
  }
  if (!reports.length || reports.at(-1)?.filing_id !== data.periodic.filing_id) throw new Error('Latest reviewed period is missing')
  return total
}

export function andersonDonationPeriods() {
  const through = andersonSource(data.periodic.filing_id).period_end!
  return {
    later: data.rapid_receipts.filter(receipt => receipt.received_date > through),
    earlier: data.rapid_receipts.filter(receipt => receipt.received_date <= through),
  }
}

/** Exact reported payee names only; this does not resolve corporate identities. */
export function andersonPaymentGroups() {
  const groups = new Map<string, { name: string; cents: number; descriptions: string[] }>()
  for (const payment of data.payments) {
    const group = groups.get(payment.payee_name) ?? { name: payment.payee_name, cents: 0, descriptions: [] }
    group.cents += reportedCents(payment.amount)
    if (!group.descriptions.includes(payment.reported_description)) group.descriptions.push(payment.reported_description)
    groups.set(payment.payee_name, group)
  }
  return [...groups.values()].sort((a, b) => b.cents - a.cents || a.name.localeCompare(b.name))
}

/** New metadata never silently replaces source-checked amounts. */
export function hasNewAndersonReports(coverage: CandidateFilingCoverage): boolean {
  const reviewed = new Set(data.sources.map(source => source.filing_id))
  return coverage.latestPeriodic.id !== data.periodic.filing_id
    || coverage.recentRapid.some(source => !reviewed.has(source.id))
}
