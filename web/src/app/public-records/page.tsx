import type { Metadata } from 'next'
import { getPublicRecordsStats, getAllPublicRecords } from '@/lib/queries'
import PublicRecordsClient from '@/components/PublicRecordsClient'
import LastUpdated from '@/components/LastUpdated'

export const revalidate = 3600 // Revalidate every hour

export const metadata: Metadata = {
  title: 'Public Records',
  description: 'CPRA compliance dashboard — track Richmond public records request response times and department performance.',
}

const EMPTY_STATS = { totalRequests: 0, avgResponseDays: 0, onTimeRate: 0, currentlyOverdue: 0 }

export default async function PublicRecordsPage() {
  // Gracefully handle missing table (migration 003 may not be run yet)
  let stats = EMPTY_STATS
  let requests: Awaited<ReturnType<typeof getAllPublicRecords>> = []
  try {
    ;[stats, requests] = await Promise.all([
      getPublicRecordsStats(),
      getAllPublicRecords(),
    ])
  } catch (e) {
    console.error('Failed to fetch public records data:', e)
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-3xl font-bold text-civic-navy">Public Records</h1>
      <p className="text-slate-600 mt-2 mb-8">
        Tracking Richmond&apos;s response to California Public Records Act (CPRA) requests.
        Under CPRA, agencies must respond within 10 calendar days.
      </p>

      <PublicRecordsClient requests={requests} stats={stats} />

      {/* Methodology note */}
      <section className="mt-10 bg-slate-50 rounded-lg p-6 border border-slate-200">
        <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">About This Data</h3>
        <p className="text-sm text-slate-600 mt-2">
          Data comes from Richmond&apos;s{' '}
          <a
            href="https://cityofrichmondca.nextrequest.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-civic-navy hover:underline"
          >
            NextRequest portal
          </a>
          . &quot;On-time&quot; means the city responded within 10 calendar days of submission.
          Some requests may have legitimate extensions under CPRA.
          This page tracks response patterns, not legal compliance determinations.
        </p>
      </section>

      <LastUpdated />
    </div>
  )
}
