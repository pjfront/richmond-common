import type { FinanceCoverage } from '@/lib/queries/finance-public'
import { formatCivicDate } from '@/lib/november-election'

const forms: Record<string, string> = {
  F460A: 'Periodic cash contributions received (Form 460, Schedule A)',
  F460C: 'Periodic noncash contributions (Form 460, Schedule C)',
  F460B1: 'Loans received (Form 460, Schedule B1)',
  F460H: 'Loans made (Form 460, Schedule H)',
  F496P3: 'Funding received by outside spenders (Form 496, Part 3)',
  S496: 'Rapid outside-spending reports (Form 496)',
  F497P1: 'Rapid contribution receipts (Form 497, Part 1)',
  F497P2: 'Rapid contributions made (Form 497, Part 2)',
}

export default function FinanceCoverageNote({ coverage }: { coverage: FinanceCoverage[] }) {
  return <details className="mt-4 rounded-lg border border-slate-200 px-4 text-sm text-slate-600">
    <summary className="min-h-11 cursor-pointer py-3 font-medium text-slate-700">Which reports are included, and when were they checked?</summary>
    <p className="mb-3 leading-relaxed">These source checks and review counts cover the whole Richmond index, across all committees and search filters.</p>
    <p className="mb-3 leading-relaxed">This is a partial index of Richmond&apos;s electronic filings. Paper reports and reports filed only with another agency may be missing. Outside spending currently comes from rapid reports; periodic spending reports are not yet included. Records with conflicting descriptions or possible repetition wait for review.</p>
    {coverage.length ? <ul className="divide-y divide-slate-200">{coverage.map(row => <li key={`${row.source}:${row.form_type}:${row.scope_key}`} className="py-3">
      <p className="font-medium text-slate-700">{forms[row.form_type] ?? row.form_type}</p>
      <p className="mt-1">{row.status === 'unavailable' ? 'Source check unavailable' : `Source checked ${formatCivicDate(row.checked_at)}`} · activity searched {row.activity_from ? formatCivicDate(row.activity_from) : 'start not published'} through {row.activity_through ? formatCivicDate(row.activity_through) : 'cutoff not published'}.</p>
      {row.pending_count > 0 && <p className="mt-1">{row.pending_count} source {row.pending_count === 1 ? 'entry awaits' : 'entries await'} review. These are report entries, not a count of separate payments or people.</p>}
      <a className="inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4" href={row.source_url}>Open the official filing portal</a>
    </li>)}</ul> : <p className="mb-4">Dated source coverage is unavailable. The displayed records do not establish a complete history.</p>}
  </details>
}
