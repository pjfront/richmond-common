import Link from 'next/link'
import { Suspense } from 'react'
import CommonsSearchClient from '@/components/CommonsSearchClient'
import LegacyResidentHome from '@/components/LegacyResidentHome'
import { isReadOnlyStage } from '@/lib/read-only-stage'

// Preserve the existing resident home until an intentional public relaunch.
export const revalidate = 3600

export default async function HomePage() {
  return isReadOnlyStage() ? <SearchFirstHome /> : LegacyResidentHome()
}

function SearchFirstHome() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6 sm:py-16 lg:px-8">
      <section aria-labelledby="search-heading">
        <p className="mb-4 text-sm font-semibold uppercase tracking-wider text-civic-navy">Richmond, California</p>
        <h1 id="search-heading" className="max-w-3xl text-4xl font-bold leading-tight tracking-tight text-civic-navy sm:text-5xl">Find the public record.</h1>
        <p className="mt-5 max-w-2xl text-lg leading-relaxed text-slate-700">Search agenda items, see how the council voted, and follow reported campaign money. Open the original records behind each result.</p>
        <div className="mt-8 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
          <Suspense fallback={<SearchLoading />}>
            <CommonsSearchClient />
          </Suspense>
        </div>
      </section>
      <section aria-labelledby="browse-heading" className="mt-12 border-t border-slate-200 pt-8">
        <h2 id="browse-heading" className="text-xl font-semibold text-civic-navy">Prefer to browse?</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <Link href="/meetings" className="rounded-lg border border-slate-200 bg-white p-5 hover:border-civic-navy sm:p-6">
            <h3 className="text-lg font-semibold text-civic-navy">Meetings <span aria-hidden="true">→</span></h3>
            <p className="mt-2 leading-relaxed text-slate-700">Read an agenda in meeting order, then open an item and its recorded votes.</p>
          </Link>
          <Link href="/money" className="rounded-lg border border-slate-200 bg-white p-5 hover:border-civic-navy sm:p-6">
            <h3 className="text-lg font-semibold text-civic-navy">Campaign money <span aria-hidden="true">→</span></h3>
            <p className="mt-2 leading-relaxed text-slate-700">Look up reported contributions and spending, with dates, source filings, and coverage limits.</p>
          </Link>
        </div>
      </section>
    </div>
  )
}

function SearchLoading() {
  return (
    <div aria-live="polite" aria-busy="true">
      <p className="mb-3 font-medium text-slate-700">Loading search…</p>
      <div aria-hidden="true" className="h-12 rounded-md bg-slate-100" />
      <div aria-hidden="true" className="mt-4 h-11 w-48 rounded-md bg-slate-100" />
    </div>
  )
}
