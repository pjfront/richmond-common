import Link from 'next/link'
import type { DonorProfile } from '@/lib/types'

export default function DonorList({ donors }: { donors: DonorProfile[] }) {
  return <>
    <header className="mb-6">
      <h1 className="text-3xl font-bold text-civic-navy">Historical donor records</h1>
      <p className="mt-3 leading-relaxed text-slate-700">Open a name to read the dated entries and original campaign reports.</p>
      <Link href="/elections/2026-general/money" className="mt-2 inline-flex min-h-11 items-center text-civic-navy underline">Search the 2026 campaign-money records →</Link>
    </header>
    <p className="mb-5 text-sm leading-relaxed text-slate-600">This alphabetical directory contains selected names from our historical donor index. It is a selection of records, not a ranking or a complete list of Richmond donors.</p>
    {donors.length ? <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200">
      {donors.map(donor => <li key={donor.donor_id}>
        <Link href={`/donors/${donor.slug}`} className="flex min-h-11 items-center justify-between gap-4 p-4 text-civic-navy hover:bg-slate-50">
          <span>{donor.display_name}</span><span aria-hidden="true">→</span>
        </Link>
      </li>)}
    </ul> : <p className="text-slate-600">No historical donor profiles are available in this directory.</p>}
  </>
}
