import type { Metadata } from 'next'
import { getPublicRecordsSnapshot } from '@/lib/queries'
import PublicRecordsClient from '@/components/PublicRecordsClient'
import LastUpdated from '@/components/LastUpdated'


export const metadata: Metadata = {
  title: 'Public Records',
  description: 'Browse Richmond public-records requests, their reported status, and links to the original NextRequest records.',
}

export default async function PublicRecordsPage() {
  return <PublicRecordsContent />
}

async function PublicRecordsContent() {
  // A failed refresh must preserve ISR's previous successful page, not publish zeros.
  const { stats, requests } = await getPublicRecordsSnapshot()

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-3xl font-bold text-civic-navy">Public Records</h1>
      <p className="text-slate-600 mt-2 mb-8">
        Browse requests in Richmond&apos;s public-records portal and open the original request to read its documents and correspondence.
      </p>

      <PublicRecordsClient requests={requests} stats={stats} />

      {/* Methodology note */}
      <section className="mt-10 bg-slate-50 rounded-lg p-6 border border-slate-200">
        <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">About This Data</h2>
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
          . Dates and statuses describe the records available here. A closed request does not establish when the city first responded or whether it met a legal deadline.
        </p>
      </section>

      <LastUpdated />
    </div>
  )
}
