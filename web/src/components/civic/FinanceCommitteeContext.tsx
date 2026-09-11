import Link from 'next/link'
import organizations from '@/data/committee-organization-filings.json'
import { financeFilterParams } from '@/lib/finance-ledger'
import { formatCivicDate } from '@/lib/november-election'

const linkClass = 'inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4'

export default function FinanceCommitteeContext({ committee }: { committee: string }) {
  const selected = organizations.committees.find(row => row.fppc_id === committee)
  if (!selected) return <nav aria-label="Outside groups with checked organization reports" className="mt-5 border-t border-slate-200 pt-4">
    <p className="font-medium text-slate-700">Explore two outside groups with checked organization reports</p>
    <div className="flex flex-col items-start sm:flex-row sm:gap-6">{organizations.committees.map(row =>
      <Link key={row.fppc_id} className={linkClass} href={`?committee=${row.fppc_id}`}>{row.display_name} →</Link>)}</div>
  </nav>

  return <section aria-labelledby="committee-name" className="mt-6 rounded-lg border border-slate-200 p-5 sm:p-6">
    <h2 id="committee-name" className="text-xl font-semibold text-civic-navy">{selected.display_name}</h2>
    <p className="mt-2 text-sm text-slate-600">FPPC {selected.fppc_id} · {selected.committee_type}</p>
    <p className="mt-4 leading-relaxed text-slate-700">The organization report listed by the city on {formatCivicDate(selected.source.filed_at)} names these sponsors:</p>
    <ul className="mt-2 space-y-1">{selected.sponsors.map(sponsor => <li key={sponsor.name}>
      <a href={`${selected.source.source_url}#page=${sponsor.page}`} className={linkClass}>{sponsor.name}</a>
      <span className="text-sm text-slate-600"> — {sponsor.affiliation.toLocaleLowerCase('en-US')} as reported</span>
    </li>)}</ul>
    <p className="mt-3 leading-relaxed text-slate-700">{selected.purpose} <a href={`${selected.source.source_url}#page=${selected.purpose_page}`} className={linkClass}>Read its stated purpose</a></p>
    <p className="mt-3 text-sm leading-relaxed text-slate-600">A sponsor is a relationship the committee reports about its organization; a donor is a source of money. One does not establish the other. This report does not identify which election an individual expense concerns.</p>
    <nav aria-label={`Follow money reported by ${selected.display_name}`} className="mt-4 flex flex-wrap gap-x-6">
      <Link href={`?${financeFilterParams({ committee, role: 'recipient' })}#records`} className={linkClass}>Money reported received →</Link>
      <Link href={`?${financeFilterParams({ committee, activity: 'independent_expenditure', role: 'source' })}#records`} className={linkClass}>Outside spending reported →</Link>
    </nav>
    <details className="mt-2 text-sm text-slate-600"><summary className="min-h-11 cursor-pointer py-3">Legal name and source check</summary>
      <p className="mt-2 break-words">{selected.reported_name}</p>
      <p className="mt-2">Organization report (Form 410), filing {selected.source.filing_id}. Original pages checked {formatCivicDate(organizations.checked_at)}. Later changes wait for review before this explanation changes.</p>
      <a className={linkClass} href={selected.source.source_url}>Open the organization report</a>
    </details>
  </section>
}
