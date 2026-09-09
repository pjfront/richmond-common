import type { DonorContribution } from './types'

/** A record date is a calendar boundary, never evidence of campaign attribution. */
export function contributionYear(date: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return null
  const parsed = new Date(`${date}T00:00:00Z`)
  return Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== date ? null : date.slice(0, 4)
}

export function availableContributionYears(records: DonorContribution[]): string[] {
  return [...new Set(records.map(record => contributionYear(record.contribution_date)))]
    .filter((year): year is string => year !== null).sort((a, b) => b.localeCompare(a))
}

export function contributionsInYear(records: DonorContribution[], year: string): DonorContribution[] {
  return year === 'all' ? records : records.filter(record => contributionYear(record.contribution_date) === year)
}

export function contributionDateRange(records: DonorContribution[]): { first: string; last: string } | null {
  const dates = records.map(record => record.contribution_date).filter(date => contributionYear(date) !== null).sort()
  return dates.length ? { first: dates[0], last: dates[dates.length - 1] } : null
}

export type HistoricalRecordKind = 'monetary' | 'noncash' | 'loan' | 'transfer' | 'refund' | 'adjustment' | 'other'
export const HISTORICAL_RECORD_LABELS: Record<HistoricalRecordKind, string> = {
  monetary: 'Recorded as monetary', noncash: 'Recorded as noncash', loan: 'Recorded as a loan',
  transfer: 'Recorded as a transfer', refund: 'Recorded as a refund',
  adjustment: 'Signed adjustment', other: 'Type not established',
}

/** Preserve the legacy classification; it is not proof of a reconciled cash gift. */
export function historicalRecordKind(record: { amount: number; contribution_type?: string | null }): HistoricalRecordKind {
  if (record.amount < 0) return 'adjustment'
  switch (record.contribution_type?.trim().toLowerCase()) {
    case 'monetary': return 'monetary'
    case 'nonmonetary': return 'noncash'
    case 'loan': return 'loan'
    case 'transfer': return 'transfer'
    case 'refund': return 'refund'
    default: return 'other'
  }
}

/** A local filing number alone cannot turn a CAL-ACCESS record into a NetFile citation. */
export function historicalFilingUrl(source: string | null | undefined, filingId: string | null | undefined): string | null {
  return source && ['city_clerk', 'netfile', 'netfile_paper'].includes(source) && filingId && /^\d{6,12}$/.test(filingId)
    ? `https://netfile.com/Connect2/api/public/image/${filingId}` : null
}

export function historicalRecordSource(record: Pick<DonorContribution, 'source' | 'filing_id' | 'source_url'>): string | null {
  const expected = historicalFilingUrl(record.source, record.filing_id)
  return expected && record.source_url === expected ? expected : null
}

/** Filter individual rows, never merge names, report amendments, or record kinds. */
export function filterHistoricalRecords(records: DonorContribution[], year: string, kind: string, search: string): DonorContribution[] {
  const query = search.trim().normalize('NFKC').toLocaleLowerCase('en-US')
  return contributionsInYear(records, year).filter(record => (kind === 'all' || historicalRecordKind(record) === kind)
    && (!query || [record.donor_name, record.donor_employer, record.committee_name, record.committee_fppc_id, record.filing_id]
      .some(value => value?.normalize('NFKC').toLocaleLowerCase('en-US').includes(query))))
}
