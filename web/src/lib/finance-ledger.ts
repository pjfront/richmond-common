import type { FinanceEvent } from './finance-public'

export function filterFinanceEvents(events: FinanceEvent[], query: string, committee: string): FinanceEvent[] {
  const search = query.trim().normalize('NFKC').toLocaleLowerCase('en-US').slice(0, 150)
  const exactId = /^\d{5,9}$/.test(committee) ? committee : ''
  return events.filter(row => {
    const ids = [row.donor_fppc_id, row.recipient_fppc_id, row.reporting_filer_fppc_id]
    if (exactId && !ids.includes(exactId)) return false
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
  const columns = ['event_key', 'event_kind', 'activity_date', 'amount', 'donor_name', 'donor_fppc_id', 'recipient_name', 'recipient_fppc_id', 'reporting_filer_name', 'reporting_filer_fppc_id', 'candidate_name', 'measure_name', 'election_date', 'support_oppose', 'filing_ids', 'source_url', 'extracted_at', 'reconciliation_status'] as const
  return [columns.join(','), ...events.map(row => columns.map(key => cell(Array.isArray(row[key]) ? row[key].join('; ') : row[key])).join(','))].join('\r\n') + '\r\n'
}
