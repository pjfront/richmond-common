import Link from 'next/link'
import { getMeetingsWithCounts, getConflictFlags } from '@/lib/queries'
import { CONFIDENCE_PUBLISHED } from '@/lib/thresholds'
import LatestMeetingCard from '@/components/LatestMeetingCard'
import HowItWorks from '@/components/HowItWorks'

export const dynamic = 'force-dynamic'
export const revalidate = 3600 // Revalidate every hour

export default async function Home() {
  const meetings = await getMeetingsWithCounts()

  const latestMeeting = meetings[0] ?? null

  // Get flag count for latest meeting
  let latestFlagCount = 0
  if (latestMeeting) {
    const flags = await getConflictFlags(latestMeeting.id)
    latestFlagCount = flags.filter((f) => f.confidence >= CONFIDENCE_PUBLISHED).length
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Hero */}
      <section className="text-center py-12">
        <h1 className="text-4xl sm:text-5xl font-bold text-civic-navy leading-tight">
          Richmond Commons
        </h1>
        <p className="text-lg text-slate-600 mt-4 max-w-2xl mx-auto">
          Your city government, in one place and in plain language.
          Meeting agendas, voting records, and campaign finance from
          official public records.
        </p>
        <div className="flex justify-center gap-4 mt-8">
          <Link
            href="/meetings"
            className="px-6 py-2.5 bg-civic-navy text-white rounded-lg font-medium hover:bg-civic-navy-light transition-colors"
          >
            Browse Meetings
          </Link>
          <Link
            href="/council"
            className="px-6 py-2.5 border border-civic-navy text-civic-navy rounded-lg font-medium hover:bg-civic-navy/5 transition-colors"
          >
            View Council
          </Link>
        </div>
      </section>

      {/* Latest Meeting */}
      {latestMeeting && (
        <section className="mb-12">
          <LatestMeetingCard
            meeting={latestMeeting}
            agendaItemCount={latestMeeting.agenda_item_count}
            voteCount={latestMeeting.vote_count}
            flagCount={latestFlagCount}
            topicLabels={latestMeeting.top_topic_labels}
          />
        </section>
      )}

      {/* How It Works */}
      <section className="mb-12 py-8 bg-slate-50 -mx-4 px-4 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8 rounded-lg">
        <HowItWorks />
      </section>

    </div>
  )
}
