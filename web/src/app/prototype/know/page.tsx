import Link from 'next/link'
import { Lora } from 'next/font/google'
import {
  getMeetingsWithCounts,
  getMostDiscussedItems,
  getTopicCounts,
  getTopicItems,
  getNextMeeting,
  getUpcomingElection,
  getMeetingStats,
  getOfficials,
} from '@/lib/queries'

const lora = Lora({
  subsets: ['latin'],
  weight: ['400', '600', '700'],
  variable: '--font-serif',
  display: 'swap',
})

export const metadata = {
  title: 'Richmond Commons — Know Your City',
  description: 'Twenty years of Richmond city government, from official records, in plain language.',
}

// ── Featured topics for knowledge threads ──
// Chosen for newcomer relevance: stories that define the city
const FEATURED_TOPICS = [
  {
    label: 'Chevron & the Refinery',
    hook: 'The refinery on the shoreline is the city\'s largest employer, taxpayer, and political spender. When Chevron is on the agenda, the community shows up ten-to-one.',
  },
  {
    label: 'Police & Community Safety',
    hook: 'From crisis response to surveillance technology, Richmond keeps renegotiating what community safety means. It\'s the most-discussed topic in city government.',
  },
  {
    label: 'Point Molate',
    hook: 'A former Navy fuel depot on the waterfront. Twenty years of developer proposals, tribal land claims, and environmental cleanup — still unresolved.',
  },
  {
    label: 'Housing & Homelessness',
    hook: 'Rent control. Housing production. Encampment policy. In a city where housing costs keep climbing, every housing decision draws attention.',
  },
]

// ── Civic regulars ──
// Hardcoded from public_comments analysis — these are public participants in public meetings.
// In production this would be a database query.
const CIVIC_REGULARS = [
  { name: 'Cordell Hindler', comments: 746, since: 2011 },
  { name: 'Mark Wassberg', comments: 347, since: 2010 },
  { name: 'Naomi Williams', comments: 294, since: 2005 },
  { name: 'Jackie Thompson', comments: 271, since: 2005 },
  { name: 'Don Gosney', comments: 198, since: 2008 },
  { name: 'Antwon Cloird', comments: 158, since: 2008 },
]

// ── Helpers ──

function shortDate(dateStr: string): string {
  return new Date(dateStr + 'T12:00:00').toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric',
  })
}

function monthDay(dateStr: string): string {
  return new Date(dateStr + 'T12:00:00').toLocaleDateString('en-US', {
    month: 'short', day: 'numeric',
  })
}

function daysUntil(dateStr: string): number {
  const target = new Date(dateStr + 'T12:00:00')
  const now = new Date()
  now.setHours(12, 0, 0, 0)
  return Math.ceil((target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
}

function firstSentence(meeting: { meeting_recap?: string | null; meeting_summary?: string | null }): string | null {
  const source = meeting.meeting_recap || meeting.meeting_summary
  if (!source) return null
  const line = source.split('\n').find(l => l.trim().length > 20)
  if (!line) return null
  return line
    .replace(/^[•\-]\s*/, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .trim()
    .slice(0, 160)
}

// ── Page ──

export default async function KnowledgeSurfacePage() {
  const [meetings, discussed, topicCounts, nextMeeting, upcomingElection, stats, officials] =
    await Promise.all([
      getMeetingsWithCounts(),
      getMostDiscussedItems(3, 120),
      getTopicCounts(),
      getNextMeeting(),
      getUpcomingElection(),
      getMeetingStats(),
      getOfficials(undefined, { councilOnly: true, currentOnly: true }),
    ])

  const latest = meetings[0]
  const latestHeadline = latest ? firstSentence(latest) : null

  // Topic count map for stats
  const topicCountMap = new Map(topicCounts.map(t => [t.topic_label, t]))

  // Fetch recent items for each featured topic
  const topicData = await Promise.all(
    FEATURED_TOPICS.map(async (ft) => {
      const items = await getTopicItems(ft.label, 3)
      const counts = topicCountMap.get(ft.label)
      return { ...ft, items, counts }
    }),
  )

  const meetingDays = nextMeeting ? daysUntil(nextMeeting.meeting_date) : null
  const electionDays = upcomingElection ? daysUntil(upcomingElection.election_date) : null

  return (
    <div className={`min-h-screen bg-[#faf9f6] ${lora.variable}`}>

      {/* ═══════════════════════════════════════════
          MASTHEAD
          ═══════════════════════════════════════════ */}
      <header className="border-b border-[#e8e3dc]">
        <div className="max-w-3xl mx-auto px-6 py-5 flex items-end justify-between">
          <div>
            <Link href="/prototype" className="text-[#a09888] text-xs tracking-widest uppercase hover:text-[#6b6358] transition-colors">
              Prototype
            </Link>
            <h1 className="text-2xl font-bold text-[#1a1a1a] tracking-tight mt-0.5" style={{ fontFamily: 'var(--font-serif), Georgia, serif' }}>
              Richmond Commons
            </h1>
          </div>
          <p className="text-sm text-[#a09888] hidden sm:block">
            Richmond, California
          </p>
        </div>
      </header>

      <div className="max-w-3xl mx-auto px-6">

        {/* ═══════════════════════════════════════════
            SEARCH HERO
            ═══════════════════════════════════════════ */}
        <section className="pt-12 pb-10">
          <h2
            className="text-3xl sm:text-[2.5rem] font-bold text-[#1a1a1a] leading-[1.15] tracking-tight"
            style={{ fontFamily: 'var(--font-serif), Georgia, serif' }}
          >
            Know your city.
          </h2>
          <p className="mt-3 text-lg text-[#6b6358] leading-relaxed max-w-lg">
            Twenty years of Richmond city government — meetings, votes, public testimony, and campaign money — from official records, in plain language.
          </p>
          <form action="/search" method="get" className="mt-6">
            <div className="relative">
              <input
                type="text"
                name="q"
                placeholder="Search a name, topic, or address…"
                className="w-full px-5 py-4 text-base bg-white border border-[#d4cec5] rounded-lg
                  text-[#1a1a1a] placeholder:text-[#b5ad9e]
                  focus:outline-none focus:border-[#2d5f4f] focus:ring-2 focus:ring-[#2d5f4f]/10
                  transition-all"
              />
              <button
                type="submit"
                className="absolute right-3 top-1/2 -translate-y-1/2 px-4 py-2 text-sm font-medium
                  bg-[#2d5f4f] text-white rounded-md hover:bg-[#24503f] transition-colors"
              >
                Search
              </button>
            </div>
          </form>
        </section>

        {/* ═══════════════════════════════════════════
            HEARTBEAT — what just happened + what's coming
            ═══════════════════════════════════════════ */}
        <section className="pb-10">
          <div className="bg-white border border-[#e8e3dc] rounded-lg overflow-hidden">
            {/* Last meeting */}
            {latest && (
              <div className="px-5 py-4 border-b border-[#e8e3dc]">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-[#2d5f4f] uppercase tracking-[0.12em] mb-1.5">
                      Latest from City Hall
                    </p>
                    <Link href={`/meetings/${latest.id}`}>
                      <p className="text-[15px] font-medium text-[#1a1a1a] leading-snug hover:text-[#2d5f4f] transition-colors">
                        {latestHeadline || `Council met ${shortDate(latest.meeting_date)}`}
                      </p>
                    </Link>
                  </div>
                  <time
                    dateTime={latest.meeting_date}
                    className="text-xs text-[#a09888] shrink-0 mt-0.5"
                  >
                    {monthDay(latest.meeting_date)}
                  </time>
                </div>
              </div>
            )}

            {/* Coming up */}
            <div className="px-5 py-3 flex flex-wrap gap-x-8 gap-y-2 bg-[#fdfcfa]">
              {nextMeeting && meetingDays !== null && meetingDays > 0 && (
                <div className="flex items-center gap-2">
                  <span className="text-lg font-bold text-[#2d5f4f] tabular-nums">{meetingDays}d</span>
                  <span className="text-sm text-[#6b6358]">to next meeting</span>
                </div>
              )}
              {upcomingElection && electionDays !== null && electionDays > 0 && (
                <div className="flex items-center gap-2">
                  <span className="text-lg font-bold text-[#8b5e3c] tabular-nums">{electionDays}d</span>
                  <Link
                    href={`/elections/${upcomingElection.election_date.slice(0, 4)}-${upcomingElection.election_type}`}
                    className="text-sm text-[#6b6358] hover:text-[#8b5e3c] transition-colors"
                  >
                    to {upcomingElection.election_name || 'election'}
                  </Link>
                </div>
              )}
              {latest?.minutes_url && (
                <a
                  href={latest.minutes_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-[#a09888] underline decoration-[#d4cec5] underline-offset-2 hover:text-[#6b6358] transition-colors"
                >
                  Minutes
                </a>
              )}
              {latest?.agenda_url && (
                <a
                  href={latest.agenda_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-[#a09888] underline decoration-[#d4cec5] underline-offset-2 hover:text-[#6b6358] transition-colors"
                >
                  Agenda
                </a>
              )}
            </div>
          </div>
        </section>

        <div className="h-px bg-[#e8e3dc]" />

        {/* ═══════════════════════════════════════════
            KNOWLEDGE THREADS — the stories of this city
            ═══════════════════════════════════════════ */}
        <section className="py-10">
          <h3
            className="text-xl font-bold text-[#1a1a1a] mb-1"
            style={{ fontFamily: 'var(--font-serif), Georgia, serif' }}
          >
            The stories of this city
          </h3>
          <p className="text-sm text-[#a09888] mb-8">
            Every topic links to the full record — every agenda item, every vote, every public comment.
          </p>

          <div className="space-y-6">
            {topicData.map(({ label, hook, items, counts }) => {
              const slug = label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/-+$/, '')
              const totalItems = counts?.item_count ?? 0
              return (
                <article key={label} className="bg-white border border-[#e8e3dc] rounded-lg overflow-hidden">
                  {/* Thread header */}
                  <div className="px-5 pt-5 pb-4">
                    <Link href={`/topics/${slug}`}>
                      <h4
                        className="text-lg font-bold text-[#1a1a1a] hover:text-[#2d5f4f] transition-colors"
                        style={{ fontFamily: 'var(--font-serif), Georgia, serif' }}
                      >
                        {label}
                      </h4>
                    </Link>
                    <p className="mt-1.5 text-sm text-[#6b6358] leading-relaxed">
                      {hook}
                    </p>
                    {totalItems > 0 && (
                      <p className="mt-2 text-xs text-[#a09888]">
                        {totalItems} agenda items since {counts?.latest_meeting_date
                          ? new Date(counts.latest_meeting_date.slice(0, 4) + '-01-01').getFullYear() - 20 + ''
                          : '2005'
                        }
                      </p>
                    )}
                  </div>

                  {/* Recent items mini-timeline */}
                  {items.length > 0 && (
                    <div className="border-t border-[#f0ece6] px-5 py-3 bg-[#fdfcfa]">
                      <p className="text-[11px] font-semibold text-[#a09888] uppercase tracking-[0.1em] mb-2.5">
                        Recent
                      </p>
                      <div className="space-y-2">
                        {items.map((item) => (
                          <Link
                            key={item.id}
                            href={`/meetings/${item.meeting_id}/items/${item.id}`}
                            className="flex items-baseline gap-3 group"
                          >
                            <time className="text-xs text-[#b5ad9e] shrink-0 w-14 text-right tabular-nums">
                              {monthDay(item.meeting_date)}
                            </time>
                            <span className="text-sm text-[#3a3530] group-hover:text-[#2d5f4f] transition-colors leading-snug">
                              {item.summary_headline || (item.title.length > 90 ? item.title.slice(0, 87) + '…' : item.title)}
                            </span>
                            {item.public_comment_count > 0 && (
                              <span className="text-xs text-[#b5ad9e] shrink-0">
                                {item.public_comment_count} spoke
                              </span>
                            )}
                          </Link>
                        ))}
                      </div>
                      <Link
                        href={`/topics/${slug}`}
                        className="inline-block mt-3 text-xs font-medium text-[#2d5f4f] hover:text-[#1a4030] transition-colors"
                      >
                        Full timeline →
                      </Link>
                    </div>
                  )}
                </article>
              )
            })}
          </div>

          <div className="mt-6 flex flex-wrap gap-2">
            {topicCounts
              .filter(t => !FEATURED_TOPICS.some(ft => ft.label === t.topic_label))
              .slice(0, 8)
              .map(topic => (
                <Link
                  key={topic.topic_label}
                  href={`/topics/${topic.topic_label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/-+$/, '')}`}
                  className="text-sm px-3 py-1.5 rounded-md bg-[#f0ece6] text-[#6b6358]
                    hover:bg-[#e8e3dc] hover:text-[#3a3530] transition-colors"
                >
                  {topic.topic_label}
                </Link>
              ))}
          </div>
        </section>

        <div className="h-px bg-[#e8e3dc]" />

        {/* ═══════════════════════════════════════════
            COMMUNITY VOICE — who's talking right now
            ═══════════════════════════════════════════ */}
        {discussed.length > 0 && (
          <section className="py-10">
            <h3
              className="text-xl font-bold text-[#1a1a1a] mb-6"
              style={{ fontFamily: 'var(--font-serif), Georgia, serif' }}
            >
              People showed up for
            </h3>
            <div className="space-y-4">
              {discussed.map((item) => (
                <Link
                  key={item.agenda_item_id}
                  href={`/meetings/${item.meeting_id}/items/${item.agenda_item_id}`}
                  className="block group"
                >
                  <p className="text-[15px] font-medium text-[#1a1a1a] leading-snug group-hover:text-[#2d5f4f] transition-colors">
                    {item.summary_headline || item.title}
                  </p>
                  <p className="text-sm text-[#a09888] mt-0.5">
                    {item.public_comment_count} public speakers · {monthDay(item.meeting_date)}
                  </p>
                </Link>
              ))}
            </div>
          </section>
        )}

        <div className="h-px bg-[#e8e3dc]" />

        {/* ═══════════════════════════════════════════
            CIVIC REGULARS — the people who hold government accountable
            ═══════════════════════════════════════════ */}
        <section className="py-10">
          <h3
            className="text-xl font-bold text-[#1a1a1a] mb-1"
            style={{ fontFamily: 'var(--font-serif), Georgia, serif' }}
          >
            The people who show up
          </h3>
          <p className="text-sm text-[#a09888] mb-6">
            Public comment is how residents hold government accountable. These Richmond residents have spoken at city council more than anyone else in the record.
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {CIVIC_REGULARS.map((person) => (
              <div key={person.name} className="bg-white border border-[#e8e3dc] rounded-lg p-4">
                <p className="font-semibold text-sm text-[#1a1a1a]">{person.name}</p>
                <p className="text-xs text-[#a09888] mt-1">
                  {person.comments} comments since {person.since}
                </p>
              </div>
            ))}
          </div>
        </section>

        <div className="h-px bg-[#e8e3dc]" />

        {/* ═══════════════════════════════════════════
            YOUR COUNCIL
            ═══════════════════════════════════════════ */}
        <section className="py-10">
          <h3
            className="text-xl font-bold text-[#1a1a1a] mb-6"
            style={{ fontFamily: 'var(--font-serif), Georgia, serif' }}
          >
            Your council
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {officials.filter(o => o.is_current).map((o) => {
              const slug = o.name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '')
              const initials = o.name.split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase()
              const isMayor = o.role === 'mayor'
              return (
                <Link
                  key={o.id}
                  href={`/council/${slug}`}
                  className="group text-center"
                >
                  <div className={`w-12 h-12 rounded-full mx-auto flex items-center justify-center text-sm font-bold transition-all
                    ${isMayor ? 'bg-[#2d5f4f] text-white' : 'bg-[#e8e3dc] text-[#6b6358]'}
                    group-hover:ring-2 group-hover:ring-[#2d5f4f]/20`}
                  >
                    {initials}
                  </div>
                  <p className="mt-2 text-sm font-medium text-[#1a1a1a] group-hover:text-[#2d5f4f] transition-colors">
                    {o.name.split(' ').slice(-1)[0]}
                  </p>
                  {isMayor && (
                    <p className="text-xs text-[#a09888]">Mayor</p>
                  )}
                </Link>
              )
            })}
          </div>
        </section>

        <div className="h-px bg-[#e8e3dc]" />

        {/* ═══════════════════════════════════════════
            WHAT WE KNOW — platform scope / credibility
            ═══════════════════════════════════════════ */}
        <section className="py-10">
          <h3
            className="text-xl font-bold text-[#1a1a1a] mb-1"
            style={{ fontFamily: 'var(--font-serif), Georgia, serif' }}
          >
            What Richmond Commons knows
          </h3>
          <p className="text-sm text-[#a09888] mb-6">
            All from official city records. Updated after every council meeting.
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[
              { value: stats.yearsOfMeetings, label: 'years of records' },
              { value: stats.meetings, label: 'meetings' },
              { value: stats.publicComments.toLocaleString(), label: 'public comments' },
              { value: stats.contributions.toLocaleString(), label: 'campaign contributions' },
            ].map(({ value, label }) => (
              <div key={label}>
                <p className="text-2xl font-bold text-[#2d5f4f] tabular-nums" style={{ fontFamily: 'var(--font-serif), Georgia, serif' }}>
                  {value}
                </p>
                <p className="text-sm text-[#6b6358] mt-0.5">{label}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ═══════════════════════════════════════════
            FOOTER
            ═══════════════════════════════════════════ */}
        <footer className="py-8 border-t border-[#e8e3dc] text-center">
          <div className="flex justify-center gap-6">
            <Link href="/meetings" className="text-sm text-[#a09888] hover:text-[#2d5f4f] transition-colors">
              All meetings
            </Link>
            <Link href="/council" className="text-sm text-[#a09888] hover:text-[#2d5f4f] transition-colors">
              Council
            </Link>
            <Link href="/about" className="text-sm text-[#a09888] hover:text-[#2d5f4f] transition-colors">
              About
            </Link>
          </div>
          <p className="text-xs text-[#c1bab0] mt-3">
            From official city records · richmondcommons.org
          </p>
        </footer>
      </div>
    </div>
  )
}
