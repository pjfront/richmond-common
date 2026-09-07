import type { DonorAggregate, DonorContribution } from './types'

/** A record date is a calendar boundary, never evidence of campaign attribution. */
export function contributionYear(date: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return null
  const parsed = new Date(`${date}T00:00:00Z`)
  return Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== date
    ? null
    : date.slice(0, 4)
}

export function availableContributionYears(records: DonorContribution[]): string[] {
  return [...new Set(records.map(record => contributionYear(record.contribution_date)))]
    .filter((year): year is string => year !== null)
    .sort((a, b) => b.localeCompare(a))
}

export function contributionsInYear(records: DonorContribution[], year: string): DonorContribution[] {
  return year === 'all' ? records : records.filter(record => contributionYear(record.contribution_date) === year)
}

/** Sum the database's two-decimal amounts as integer cents, including signed entries. */
export function sumRecordedAmounts(amounts: number[]): number {
  let totalCents = 0
  for (const amount of amounts) {
    if (!Number.isFinite(amount)) throw new Error('Invalid historical contribution amount')
    const cents = Math.round(amount * 100)
    if (!Number.isSafeInteger(cents)) throw new Error('Invalid historical contribution amount')
    totalCents += cents
    if (!Number.isSafeInteger(totalCents)) throw new Error('Historical contribution amount exceeds supported range')
  }
  return totalCents / 100
}

export function aggregateDonorRecords(records: DonorContribution[]): DonorAggregate[] {
  const donors = new Map<string, DonorAggregate>()
  for (const record of records) {
    const existing = donors.get(record.donor_name)
    if (existing) {
      existing.total_amount = sumRecordedAmounts([existing.total_amount, record.amount])
      existing.contribution_count += 1
    } else {
      donors.set(record.donor_name, {
        donor_name: record.donor_name,
        donor_employer: record.donor_employer,
        total_amount: sumRecordedAmounts([record.amount]),
        contribution_count: 1,
        source: record.source,
        donor_pattern: record.donor_pattern,
      })
    }
  }
  return [...donors.values()].sort((a, b) => b.total_amount - a.total_amount)
}

export function searchDonorRecords(donors: DonorAggregate[], search: string): DonorAggregate[] {
  const query = search.trim().toLowerCase()
  return query ? donors.filter(donor => donor.donor_name.toLowerCase().includes(query)
    || donor.donor_employer?.toLowerCase().includes(query)) : donors
}

export function contributionDateRange(records: DonorContribution[]): { first: string; last: string } | null {
  const dates = records.map(record => record.contribution_date).filter(date => contributionYear(date) !== null).sort()
  return dates.length ? { first: dates[0], last: dates[dates.length - 1] } : null
}

export interface DonorRecordSource {
  key: string
  committeeName: string
  committeeFppcId: string | null
  filingId: string | null
  sourceUrl: string | null
  recordCount: number
  recordedAmount: number
  dateRange: { first: string; last: string } | null
  recordTypes: string[]
}

export function donorRecordSources(records: DonorContribution[]): DonorRecordSource[] {
  const groups = new Map<string, DonorContribution[]>()
  for (const record of records) {
    const key = JSON.stringify([record.committee_fppc_id ?? null, record.committee_name ?? null, record.filing_id ?? null])
    const group = groups.get(key) ?? []
    group.push(record)
    groups.set(key, group)
  }
  return [...groups.entries()].map(([key, group]) => {
    const first = group[0]
    const filingId = first.filing_id && /^\d{6,12}$/.test(first.filing_id) ? first.filing_id : null
    const officialUrl = filingId ? `https://netfile.com/Connect2/api/public/image/${filingId}` : null
    return {
      key,
      committeeName: first.committee_name || 'Committee not identified in these records',
      committeeFppcId: first.committee_fppc_id || null,
      filingId,
      sourceUrl: officialUrl && group.some(record => record.source_url === officialUrl) ? officialUrl : null,
      recordCount: group.length,
      recordedAmount: sumRecordedAmounts(group.map(record => record.amount)),
      dateRange: contributionDateRange(group),
      recordTypes: [...new Set(group.map(record => record.contribution_type).filter((type): type is string => Boolean(type)))].sort(),
    }
  }).sort((a, b) => a.committeeName.localeCompare(b.committeeName) || (b.dateRange?.last ?? '').localeCompare(a.dateRange?.last ?? '') || a.key.localeCompare(b.key))
}
