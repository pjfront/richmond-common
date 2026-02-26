import type { Metadata } from 'next'
import { getMeetingsWithCounts } from '@/lib/queries'
import MeetingsPageClient from '@/components/MeetingsPageClient'
import LastUpdated from '@/components/LastUpdated'

export const revalidate = 3600 // Revalidate every hour

export const metadata: Metadata = {
  title: 'Meetings',
  description: 'Richmond City Council meeting minutes with voting records and attendance.',
}

export default async function MeetingsPage() {
  const meetings = await getMeetingsWithCounts()

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-3xl font-bold text-civic-navy">Council Meetings</h1>
      <p className="text-slate-600 mt-2">
        Extracted from official city council minutes. Click a meeting to see agenda items, votes, and attendance.
      </p>
      <MeetingsPageClient meetings={meetings} />
      <LastUpdated />
    </div>
  )
}
