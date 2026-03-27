import type { Metadata } from 'next'
import { Suspense } from 'react'
import { getMeetingsWithCounts, getMeetingFlagCounts } from '@/lib/queries'
import MeetingsDiscovery from '@/components/MeetingsDiscovery'
import LastUpdated from '@/components/LastUpdated'

export const dynamic = 'force-dynamic'
export const revalidate = 3600 // Revalidate every hour

export const metadata: Metadata = {
  title: 'Meetings',
  description: 'Richmond City Council meeting minutes with voting records and attendance.',
}

export default async function MeetingsPage() {
  const [meetings, flagCountMap] = await Promise.all([
    getMeetingsWithCounts(),
    getMeetingFlagCounts(),
  ])

  // Convert Map to plain object for server→client serialization
  const flagCounts = Object.fromEntries(flagCountMap)

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      <h1 className="text-4xl font-bold text-civic-navy">Council Meetings</h1>
      <p className="text-sm text-slate-500 mt-2 mb-8">
        From official city council minutes and agendas.
      </p>
      <Suspense fallback={<div className="py-8 text-slate-400">Loading meetings...</div>}>
        <MeetingsDiscovery meetings={meetings} flagCounts={flagCounts} />
      </Suspense>
      <LastUpdated />
    </div>
  )
}
