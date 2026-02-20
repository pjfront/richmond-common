import Link from 'next/link'
import { getMeetingStats, getMeetingsWithCounts, getConflictFlags } from '@/lib/queries'
import StatsBar from '@/components/StatsBar'
import LatestMeetingCard from '@/components/LatestMeetingCard'
import HowItWorks from '@/components/HowItWorks'

export const revalidate = 3600 // Revalidate every hour

export default async function Home() {
  const [stats, meetings] = await Promise.all([
    getMeetingStats(),
    getMeetingsWithCounts(),
  ])

  const latestMeeting = meetings[0] ?? null

  // Get flag count for latest meeting
  let latestFlagCount = 0
  if (latestMeeting) {
    const flags = await getConflictFlags(latestMeeting.id)
    latestFlagCount = flags.filter((f) => f.confidence >= 0.5).length
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Hero */}
      <section className="text-center py-12">
        <h1 className="text-4xl sm:text-5xl font-bold text-civic-navy leading-tight">
          Richmond Transparency Project
        </h1>
        <p className="text-lg text-slate-600 mt-4 max-w-2xl mx-auto">
          AI-powered government accountability for Richmond, California.
          We cross-reference council agendas against campaign contributions
          so citizens can follow the money.
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

      {/* Stats */}
      <section className="mb-12">
        <StatsBar
          stats={[
            { label: 'Meetings Tracked', value: stats.meetings },
            { label: 'Votes Recorded', value: stats.votes },
            { label: 'Contributions Cross-Referenced', value: stats.contributions },
            { label: 'Conflict Flags', value: stats.conflictFlags },
          ]}
        />
      </section>

      {/* Latest Meeting */}
      {latestMeeting && (
        <section className="mb-12">
          <LatestMeetingCard
            meeting={latestMeeting}
            agendaItemCount={latestMeeting.agenda_item_count}
            voteCount={latestMeeting.vote_count}
            flagCount={latestFlagCount}
          />
        </section>
      )}

      {/* How It Works */}
      <section className="mb-12 py-8 bg-slate-50 -mx-4 px-4 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8 rounded-lg">
        <HowItWorks />
      </section>

      {/* Quick Links */}
      <section className="grid sm:grid-cols-3 gap-4">
        <Link
          href="/reports"
          className="bg-white rounded-lg border border-slate-200 p-4 hover:border-civic-navy-light transition-colors"
        >
          <h3 className="font-semibold text-slate-900">Transparency Reports</h3>
          <p className="text-sm text-slate-500 mt-1">
            View conflict-of-interest analysis for each meeting.
          </p>
        </Link>
        <Link
          href="/council"
          className="bg-white rounded-lg border border-slate-200 p-4 hover:border-civic-navy-light transition-colors"
        >
          <h3 className="font-semibold text-slate-900">Council Members</h3>
          <p className="text-sm text-slate-500 mt-1">
            Voting records, attendance, and campaign donors.
          </p>
        </Link>
        <Link
          href="/about"
          className="bg-white rounded-lg border border-slate-200 p-4 hover:border-civic-navy-light transition-colors"
        >
          <h3 className="font-semibold text-slate-900">Methodology</h3>
          <p className="text-sm text-slate-500 mt-1">
            How we collect, analyze, and publish data.
          </p>
        </Link>
      </section>
    </div>
  )
}
