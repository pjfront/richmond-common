import Link from 'next/link'
import { getMeetingsWithCounts, getConflictFlags, getOfficials, getCurrentCandidacies, getMostDiscussedItems } from '@/lib/queries'
import { CONFIDENCE_PUBLISHED } from '@/lib/thresholds'
import LatestMeetingCard from '@/components/LatestMeetingCard'
import MostDiscussedItems from '@/components/MostDiscussedItems'
import OfficialCard from '@/components/OfficialCard'


export default async function Home() {
  const [meetings, officials, candidacies, mostDiscussed] = await Promise.all([
    getMeetingsWithCounts(),
    getOfficials(undefined, { councilOnly: true }),
    getCurrentCandidacies(),
    getMostDiscussedItems(2),
  ])

  const latestMeeting = meetings[0] ?? null

  // Get flag count for latest meeting
  let latestFlagCount = 0
  if (latestMeeting) {
    const flags = await getConflictFlags(latestMeeting.id)
    latestFlagCount = flags.filter((f) => f.confidence >= CONFIDENCE_PUBLISHED).length
  }

  const currentMembers = officials.filter((o) => o.is_current)

  // Build candidacy map
  const candidacyMap = new Map<string, { office: string; electionDate: string }>()
  for (const c of candidacies) {
    if (c.official_id) {
      candidacyMap.set(c.official_id, { office: c.office_sought, electionDate: c.election_date })
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Compact hero — one line, not a marketing pitch */}
      <section className="mb-8">
        <h1 className="text-4xl font-bold text-civic-navy">Richmond Commons</h1>
        <p className="text-base text-slate-600 mt-1">
          Your city government, in one place and in plain language.
        </p>
      </section>

      {/* Latest Meeting — the real content */}
      {latestMeeting && (
        <section className="mb-10">
          <LatestMeetingCard
            meeting={latestMeeting}
            agendaItemCount={latestMeeting.agenda_item_count}
            voteCount={latestMeeting.vote_count}
            flagCount={latestFlagCount}
            topicLabels={latestMeeting.top_topic_labels}
          />
          <div className="mt-3 text-right">
            <Link
              href="/meetings"
              className="text-sm font-medium text-civic-navy hover:text-civic-navy-light transition-colors"
            >
              All meetings &rarr;
            </Link>
          </div>
        </section>
      )}

      {/* Most Discussed — community engagement signal */}
      <MostDiscussedItems items={mostDiscussed} />

      {/* Council Members — compact grid */}
      {currentMembers.length > 0 && (
        <section>
          <h2 className="text-xl font-semibold text-slate-800 mb-4">Council Members</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {currentMembers.map((o) => (
              <OfficialCard
                key={o.id}
                official={o}
                candidacy={candidacyMap.get(o.id)}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
