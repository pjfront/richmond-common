import type { Metadata } from 'next'
import { getMeetingsWithCounts } from '@/lib/queries'
import MeetingCard from '@/components/MeetingCard'
import LastUpdated from '@/components/LastUpdated'

export const revalidate = 3600 // Revalidate every hour

export const metadata: Metadata = {
  title: 'Meetings',
  description: 'Richmond City Council meeting minutes with voting records and attendance.',
}

export default async function MeetingsPage() {
  const meetings = await getMeetingsWithCounts()

  // Group by year
  const byYear = new Map<number, typeof meetings>()
  for (const m of meetings) {
    const year = new Date(m.meeting_date + 'T00:00:00').getFullYear()
    const arr = byYear.get(year) ?? []
    arr.push(m)
    byYear.set(year, arr)
  }
  const years = Array.from(byYear.keys()).sort((a, b) => b - a)

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-3xl font-bold text-civic-navy">Council Meetings</h1>
      <p className="text-slate-600 mt-2">
        Extracted from official city council minutes. Click a meeting to see agenda items, votes, and attendance.
      </p>

      {meetings.length === 0 ? (
        <p className="text-slate-500 mt-8">No meetings loaded yet.</p>
      ) : (
        years.map((year) => (
          <section key={year} className="mt-8">
            <h2 className="text-xl font-semibold text-slate-800 mb-4">{year}</h2>
            <div className="space-y-3">
              {(byYear.get(year) ?? []).map((m) => (
                <MeetingCard
                  key={m.id}
                  id={m.id}
                  meetingDate={m.meeting_date}
                  meetingType={m.meeting_type}
                  presidingOfficer={m.presiding_officer}
                  agendaItemCount={m.agenda_item_count}
                  voteCount={m.vote_count}
                  topCategories={m.top_categories}
                />
              ))}
            </div>
          </section>
        ))
      )}
      <LastUpdated />
    </div>
  )
}
