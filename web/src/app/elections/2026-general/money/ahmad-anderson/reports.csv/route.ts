import { ANDERSON_FINANCE as data, andersonSource, andersonSourcePage } from '@/lib/anderson-finance'

export const revalidate = 3600

/** Summary totals and individual disclosures are distinct rows, never one ledger. */
export function GET() {
  const rows: (string | number | null)[][] = [[
    'record_type', 'committee_fppc_id', 'period_start', 'period_end', 'received_date', 'donor_name',
    'amount_usd', 'filing_id', 'pdf_page', 'source_url', 'source_pdf_sha256', 'reviewed_at',
    'paid_date', 'payee_name', 'reported_payment_description',
  ]]
  for (const period of data.periodic_history) {
    const source = andersonSource(period.filing_id)
    rows.push(['reported_period_monetary_total', data.committee.fppc_id, source.period_start, source.period_end,
      null, null, period.monetary_received, source.filing_id, period.summary_page,
      andersonSourcePage(source.filing_id, period.summary_page), source.pdf_sha256, data.reviewed_at, null, null, null])
  }
  for (const receipt of data.rapid_receipts) {
    const source = andersonSource(receipt.filing_id)
    rows.push(['reported_contribution_disclosure_do_not_add_to_period_totals', data.committee.fppc_id,
      null, null, receipt.received_date, receipt.donor_name, receipt.amount, source.filing_id, receipt.page,
      andersonSourcePage(source.filing_id, receipt.page), source.pdf_sha256, data.reviewed_at, null, null, null])
  }
  for (const payment of data.payments) {
    const source = andersonSource(payment.filing_id)
    rows.push(['individual_payment_included_in_period_spending', data.committee.fppc_id,
      source.period_start, source.period_end, null, null, payment.amount, source.filing_id, payment.page,
      andersonSourcePage(source.filing_id, payment.page), source.pdf_sha256, data.reviewed_at,
      payment.paid_date, payment.payee_name, payment.reported_description])
  }
  const cell = (value: string | number | null) => {
    let text = value === null ? '' : String(value)
    if (/^[=+@\-\t\r]/.test(text)) text = `'${text}`
    return `"${text.replaceAll('"', '""')}"`
  }
  return new Response(rows.map(row => row.map(cell).join(',')).join('\r\n') + '\r\n', {
    headers: { 'Content-Type': 'text/csv; charset=utf-8',
      'Content-Disposition': 'attachment; filename="anderson-campaign-reported-figures.csv"',
      'Cache-Control': 'public, max-age=3600', 'X-Content-Type-Options': 'nosniff' },
  })
}
