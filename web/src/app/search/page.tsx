import type { Metadata } from 'next'
import { Suspense } from 'react'
import CommonsSearchClient from '@/components/CommonsSearchClient'

export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Search',
  description: 'Search Richmond agenda items, recorded votes, and reported campaign money, with original sources.',
}

export default function SearchPage() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6 lg:px-8">
      <h1 className="text-3xl font-bold tracking-tight text-civic-navy sm:text-4xl">Search the public record</h1>
      <p className="mt-4 max-w-2xl text-lg leading-relaxed text-slate-700">Find a decision, a recorded vote, or reported campaign money. Use a topic, name, or short question to get started.</p>
      <div className="mt-8 rounded-xl border border-slate-200 bg-white p-4 sm:p-6">
        <Suspense fallback={<div aria-live="polite" aria-busy="true"><p className="mb-3 text-slate-700">Loading search…</p><div aria-hidden="true" className="h-12 rounded-md bg-slate-100" /></div>}>
          <CommonsSearchClient />
        </Suspense>
      </div>
    </div>
  )
}
