import type { Metadata } from 'next'
import { Suspense } from 'react'
import OperatorGate from '@/components/OperatorGate'
import SearchPageClient from '@/components/SearchPageClient'

// Operator-only page — skip static prerendering, render on demand
export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Search',
  description: 'Search across agenda items, officials, commissions, and vote explanations.',
}

export default function SearchPage() {
  return (
    <OperatorGate fallback={
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-16 text-center">
        <h1 className="text-2xl font-bold text-civic-navy mb-3">Search</h1>
        <p className="text-slate-600">This feature is under development and not yet available to the public.</p>
      </div>
    }>
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-civic-navy">Search</h1>
          <p className="text-slate-600 mt-1 text-sm">
            Full-text search across Richmond city council records.
          </p>
        </div>
        <Suspense fallback={<p className="text-sm text-slate-500 text-center py-8">Loading...</p>}>
          <SearchPageClient />
        </Suspense>
      </div>
    </OperatorGate>
  )
}
