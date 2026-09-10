import type { FinanceEvent } from './queries/finance-public'

/** A signed correction does not establish that cash was refunded. */
export function isFinanceAdjustment(event: Pick<FinanceEvent, 'amount' | 'amount_kind'>): boolean {
  return event.amount < 0 || event.amount_kind.endsWith('_adjustment')
}

export function financeEventLabel(event: Pick<FinanceEvent, 'event_kind' | 'amount' | 'amount_kind'>): string {
  if (isFinanceAdjustment(event)) {
    const subjects: Record<FinanceEvent['event_kind'], string> = {
      receipt: 'cash receipts', transfer: 'contributions made', independent_expenditure: 'independent spending',
      refund: 'reported refunds', loan: 'reported loan value', noncash: 'reported noncash value',
    }
    return `Signed adjustment to ${subjects[event.event_kind]}`
  }
  const labels: Record<FinanceEvent['event_kind'], string> = {
    receipt: 'Cash contribution reported received', transfer: 'Contribution reported made', independent_expenditure: 'Independent expenditure',
    refund: 'Reported refund', loan: 'Reported loan value', noncash: 'Reported noncash value',
  }
  return labels[event.event_kind]
}

export const FINANCE_ACTIVITIES = [
  { value: '', label: 'All kinds of activity' },
  { value: 'contributions', label: 'Cash contributions' },
  { value: 'independent_expenditure', label: 'Outside spending' },
  { value: 'loan', label: 'Reported loan values' },
  { value: 'noncash', label: 'Noncash contributions' },
  { value: 'refund', label: 'Reported refunds' },
] as const

export type FinanceFilters = { q: string; committee: string; activity: string; role: string }

/** The page and CSV interpret the same URL filters. Unknown values select all. */
export function parseFinanceFilters(raw: Partial<FinanceFilters>): FinanceFilters {
  const committee = /^\d{5,9}$/.test(raw.committee ?? '') ? raw.committee! : ''
  return {
    q: (raw.q ?? '').trim().slice(0, 150), committee,
    activity: FINANCE_ACTIVITIES.some(option => option.value === raw.activity) ? raw.activity! : '',
    role: committee && ['recipient', 'source'].includes(raw.role ?? '') ? raw.role! : '',
  }
}

export function financeFilterParams(filters: Partial<FinanceFilters>): URLSearchParams {
  return new URLSearchParams(Object.entries(parseFinanceFilters(filters)).filter(([, value]) => value))
}

export function filterFinanceEvents(events: FinanceEvent[], filters: Partial<FinanceFilters> = {}): FinanceEvent[] {
  const { q, committee: exactId, activity, role } = parseFinanceFilters(filters)
  const search = q.normalize('NFKC').toLocaleLowerCase('en-US')
  return events.filter(row => {
    const ids = [row.donor_fppc_id, row.recipient_fppc_id, row.reporting_filer_fppc_id]
    if (exactId && !ids.includes(exactId)) return false
    if (activity && (activity === 'contributions'
      ? !['receipt', 'transfer'].includes(row.event_kind) : row.event_kind !== activity)) return false
    if (role === 'recipient' && (row.event_kind === 'independent_expenditure' || row.recipient_fppc_id !== exactId)) return false
    if (role === 'source' && (row.event_kind === 'independent_expenditure'
      ? row.reporting_filer_fppc_id !== exactId : row.donor_fppc_id !== exactId)) return false
    if (!search) return true
    return [...ids, row.donor_name, row.recipient_name, row.reporting_filer_name, row.candidate_name, row.measure_name]
      .some(value => value?.normalize('NFKC').toLocaleLowerCase('en-US').includes(search))
  })
}

/** Formula-neutralized, provenance-bearing CSV; private assertion payloads never enter this projection. */
export function financeCsv(events: FinanceEvent[]): string {
  const cell = (value: unknown) => {
    let text = value == null ? '' : String(value)
    if (typeof value === 'string' && /^[\s]*[=+@-]/u.test(text)) text = `'${text}`
    return `"${text.replaceAll('"', '""')}"`
  }
  const columns = ['event_key', 'scope_key', 'event_kind', 'activity_date', 'amount', 'amount_kind', 'donor_name', 'donor_fppc_id', 'recipient_name', 'recipient_fppc_id', 'reporting_filer_name', 'reporting_filer_fppc_id', 'candidate_name', 'measure_name', 'election_date', 'support_oppose', 'filing_ids', 'source_url', 'source_urls', 'extracted_at', 'reconciliation_status'] as const
  return [columns.join(','), ...events.map(row => columns.map(key => cell(Array.isArray(row[key]) ? row[key].join('; ') : row[key])).join(','))].join('\r\n') + '\r\n'
}
