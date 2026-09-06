import { unstable_cache } from 'next/cache'
import { supabase } from '@/lib/supabase'
import { isFinanceAdjustment } from '@/lib/finance-ledger'

export const PUBLIC_FINANCE_SCOPE = '0660620:calendar-2026'

export interface FinanceEvent {
  event_key: string
  scope_key: string
  event_kind: 'receipt' | 'transfer' | 'independent_expenditure' | 'refund' | 'loan' | 'noncash'
  donor_name: string | null
  donor_fppc_id: string | null
  recipient_name: string | null
  recipient_fppc_id: string | null
  reporting_filer_name: string | null
  reporting_filer_fppc_id: string | null
  amount: number
  amount_kind: string
  activity_date: string
  support_oppose: 'S' | 'O' | null
  candidate_name: string | null
  measure_name: string | null
  election_date: string | null
  filing_ids: string[]
  source_urls: string[]
  source_url: string
  extracted_at: string
  source_tier: number
  reconciliation_status: string
}

export interface FinanceCoverage {
  source: string
  form_type: string
  scope_key: string
  status: 'complete' | 'partial' | 'unavailable' | 'pending_review'
  checked_at: string
  activity_from: string | null
  activity_through: string | null
  filing_count: number
  assertion_count: number
  pending_count: number
  limitations: string[]
  source_url: string
}

export interface PublicFinanceSnapshot {
  events: FinanceEvent[]
  coverage: FinanceCoverage[]
  truncated: boolean
}

const EVENT_COLUMNS = 'event_key,scope_key,event_kind,donor_name,donor_fppc_id,recipient_name,recipient_fppc_id,reporting_filer_name,reporting_filer_fppc_id,amount,amount_kind,activity_date,support_oppose,candidate_name,measure_name,election_date,filing_ids,source_urls,source_url,extracted_at,source_tier,reconciliation_status'

/** Bounded, cached public projection; an error is thrown, never cached as zero activity. */
export const getPublicFinanceSnapshot = unstable_cache(async (): Promise<PublicFinanceSnapshot> => {
  const events: FinanceEvent[] = []
  let truncated = false
  for (let offset = 0; offset < 5000; offset += 1000) {
    const { data, error } = await supabase.from('finance_public_events').select(EVENT_COLUMNS)
      .eq('scope_key', PUBLIC_FINANCE_SCOPE)
      .gte('activity_date', '2026-01-01').lte('activity_date', '2026-11-03')
      .order('activity_date', { ascending: false }).order('event_key')
      .range(offset, offset + 999)
    if (error) throw new Error(`Finance projection unavailable (${error.code ?? 'query error'})`)
    for (const row of (data ?? []) as unknown as FinanceEvent[]) {
      const amount = Number(row.amount)
      if (!Number.isFinite(amount) || !row.amount_kind || !row.source_url || !row.extracted_at) {
        throw new Error('Finance projection contains incomplete provenance or amount')
      }
      events.push({ ...row, amount })
    }
    if ((data?.length ?? 0) < 1000) break
    if (offset === 4000) truncated = true
  }
  const { data, error } = await supabase.from('finance_public_coverage')
    .select('source,form_type,scope_key,status,checked_at,activity_from,activity_through,filing_count,assertion_count,pending_count,limitations,source_url')
    .eq('scope_key', PUBLIC_FINANCE_SCOPE)
    .order('checked_at', { ascending: false }).limit(40)
  if (error) throw new Error(`Finance source coverage unavailable (${error.code ?? 'query error'})`)
  return { events, coverage: (data ?? []) as unknown as FinanceCoverage[], truncated }
}, ['finance-public-2026-v2'], { revalidate: 900, tags: ['finance-public'] })

export function candidateMoney(events: FinanceEvent[], committeeId: string, candidateName: string) {
  const receipts = events.filter(row => row.recipient_fppc_id === committeeId && row.event_kind === 'receipt')
  const grossReceipts = receipts.filter(row => !isFinanceAdjustment(row))
  const receiptAdjustments = receipts.filter(isFinanceAdjustment)
  const outside = events.filter(row => row.event_kind === 'independent_expenditure'
    && row.candidate_name?.trim().toLocaleLowerCase('en-US') === candidateName.toLocaleLowerCase('en-US')
    && row.election_date === '2026-11-03')
  const sum = (rows: FinanceEvent[]) => rows.reduce((total, row) => total + Math.round(row.amount * 100), 0) / 100
  return { receipts, grossReceipts, receiptAdjustments, outside,
    grossReceiptsTotal: sum(grossReceipts), receiptAdjustmentsTotal: sum(receiptAdjustments), netReceiptsTotal: sum(receipts),
    support: outside.filter(row => row.support_oppose === 'S'),
    opposition: outside.filter(row => row.support_oppose === 'O'),
    supportTotal: sum(outside.filter(row => row.support_oppose === 'S')),
    oppositionTotal: sum(outside.filter(row => row.support_oppose === 'O')),
  }
}
