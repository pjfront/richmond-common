import type { Metadata } from 'next'
import { Suspense } from 'react'
import SearchPageClient from '@/components/SearchPageClient'

export const revalidate = 3600

export const metadata: Metadata = {
  title: 'Search',
  description: 'Search Richmond city council agenda items.',
}

export default function SearchPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-civic-navy">Search</h1>
        <p className="text-slate-600 mt-1 text-sm">
          Search Richmond city council agenda items.
        </p>
      </div>
      <Suspense fallback={<p className="text-sm text-slate-500 text-center py-8">Loading...</p>}>
        <SearchPageClient />
      </Suspense>
    </div>
  )
}
