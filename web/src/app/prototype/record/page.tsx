import Link from 'next/link'
import { getMeetingsWithCounts, getMostDiscussedItems, getControversialItems, getOfficials, getNextMeeting, getUpcomingElection, getTopicCounts, getTopicTaxonomy } from '@/lib/queries'

export const metadata = { title: 'The Front Page — Prototype' }

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

function recapToHeadline(meeting: { meeting_recap?: string | null; meeting_summary?: string | null }): { headline: string; deck: string | null } {
  const source = meeting.meeting_recap || meeting.meeting_summary
  if (!source) return { headline: 'Council met this week', deck: null }

  const lines = source.split('\n').filter(Boolean).map(l =>
    l.replace(/^[•\-]\s*/, '').replace(/\*\*([^*]+)\*\*/g, '$1').trim()
  )

  // First line becomes headline, second becomes deck
  const headline = lines[0]?.length > 120 ? lines[0].slice(0, 117) + '...' : lines[0] || 'Council met this week'
  const deck = lines[1] || null
  return { headline, deck }
}

function describeTally(tally: string | null): string | null {
  if (!tally) return null
  const ayeMatch = tally.match(/(?:Ayes?|Yes)\s*(?:\((\d+)\)|:\s*(\d+))/i)
  const nayMatch = tally.match(/(?:Noes?|Nays?|No)\s*(?:\((\d+)\)|:\s*(\d+))/i)
  const ayes = ayeMatch ? parseInt(ayeMatch[1] || ayeMatch[2]) : null
  const nays = nayMatch ? parseInt(nayMatch[1] || nayMatch[2]) : null
  if (ayes !== null && nays !== null) return `${ayes}–${nays}`
  return null
}

export default async function FrontPage() {
  const [meetings, discussed, controversial, officials, nextMeeting, upcomingElection, topicCounts, richmondLocalIssues] = await Promise.all([
    getMeetingsWithCounts(),
    getMostDiscussedItems(5, 120),
    getControversialItems(5),
    getOfficials(undefined, { councilOnly: true, currentOnly: true }),
    getNextMeeting(),
    getUpcomingElection(),
    getTopicCounts(),
    getTopicTaxonomy(),
  ])

  const latest = meetings[0]
  const { headline, deck } = latest ? recapToHeadline(latest) : { headline: '', deck: null }

  // Split votes from recent meetings (not the latest — we already feature that)
  const splitVotes = controversial.filter(c => c.meeting_id !== latest?.id).slice(0, 2)

  // Active topics — top 5 by recent activity
  const activeTopics = topicCounts.slice(0, 6)

  // Find matching local issue for color
  const issueMap = new Map(richmondLocalIssues.map(i => [i.label, i]))

  return (
    <div className="min-h-screen bg-[#faf9f7]">

      {/* ── Masthead ── */}
      <header className="bg-[#1a2332]">
        <div className="max-w-3xl mx-auto px-6 py-5 flex items-end justify-between">
          <div>
            <Link href="/prototype" className="text-[#7a8ba3] text-xs tracking-widest uppercase hover:text-white/60 transition-colors">
              Prototype
            </Link>
            <h1 className="text-2xl font-bold text-white tracking-tight mt-0.5">
              Richmond Commons
            </h1>
          </div>
          <p className="text-[#7a8ba3] text-sm hidden sm:block">
            Richmond, California
          </p>
        </div>
      </header>

      <div className="max-w-3xl mx-auto px-6">

        {/* ── Hero Story ── */}
        {latest && (
          <article className="pt-10 pb-8">
            <div className="flex items-center gap-2 mb-4">
              <span className="inline-block w-2 h-2 rounded-full bg-[#c4523e]" />
              <time
                dateTime={latest.meeting_date}
                className="text-sm font-medium text-[#8a7e72] tracking-wide"
              >
                {shortDate(latest.meeting_date)}
              </time>
            </div>
            <Link href={`/meetings/${latest.id}`}>
              <h2 className="text-[2rem] sm:text-[2.5rem] font-bold text-[#1a2332] leading-[1.15] tracking-tight hover:text-[#3d5a80] transition-colors">
                {headline}
              </h2>
            </Link>
            {deck && (
              <p className="mt-4 text-lg text-[#5a5347] leading-relaxed">
                {deck}
              </p>
            )}
            <div className="mt-5 flex items-center gap-4 text-sm text-[#8a7e72]">
              {latest.minutes_url && (
                <a
                  href={latest.minutes_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline decoration-[#d1cbc3] underline-offset-2 hover:text-[#5a5347] transition-colors"
                >
                  Official minutes
                </a>
              )}
              {latest.agenda_url && (
                <a
                  href={latest.agenda_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline decoration-[#d1cbc3] underline-offset-2 hover:text-[#5a5347] transition-colors"
                >
                  Agenda packet
                </a>
              )}
            </div>
          </article>
        )}

        <div className="h-px bg-[#e4dfd8]" />

        {/* ── Two-column: Community Voice + Split Votes ── */}
        <div className="grid grid-cols-1 md:grid-cols-5 gap-0 md:gap-10 py-8">

          {/* Community voice — wider column */}
          {discussed.length > 0 && (
            <section className="md:col-span-3 pb-8 md:pb-0 border-b md:border-b-0 border-[#e4dfd8]">
              <h3 className="text-xs font-bold text-[#c4523e] uppercase tracking-[0.15em] mb-5">
                Residents spoke up about
              </h3>
              <div className="space-y-5">
                {discussed.map((item, i) => (
                  <div key={item.agenda_item_id}>
                    <Link
                      href={`/meetings/${item.meeting_id}/items/${item.agenda_item_id}`}
                      className="group"
                    >
                      <h4 className="text-base font-semibold text-[#1a2332] leading-snug group-hover:text-[#3d5a80] transition-colors">
                        {item.summary_headline || item.title}
                      </h4>
                    </Link>
                    <p className="text-sm text-[#8a7e72] mt-1">
                      {item.public_comment_count} speakers · {monthDay(item.meeting_date)}
                    </p>
                    {i < discussed.length - 1 && (
                      <div className="mt-5 h-px bg-[#eeebe6]" />
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Split votes — narrower column */}
          {splitVotes.length > 0 && (
            <section className="md:col-span-2 pt-8 md:pt-0 md:border-l md:border-[#e4dfd8] md:pl-10">
              <h3 className="text-xs font-bold text-[#c4523e] uppercase tracking-[0.15em] mb-5">
                Divided votes
              </h3>
              <div className="space-y-5">
                {splitVotes.map((item) => {
                  const tally = describeTally(item.vote_tally)
                  return (
                    <div key={item.agenda_item_id}>
                      <Link
                        href={`/meetings/${item.meeting_id}`}
                        className="group"
                      >
                        <h4 className="text-sm font-semibold text-[#1a2332] leading-snug group-hover:text-[#3d5a80] transition-colors">
                          {item.title.length > 80 ? item.title.slice(0, 77) + '...' : item.title}
                        </h4>
                      </Link>
                      <p className="text-sm text-[#8a7e72] mt-1">
                        {item.result}{tally ? ` (${tally})` : ''} · {monthDay(item.meeting_date)}
                      </p>
                    </div>
                  )
                })}
              </div>
            </section>
          )}
        </div>

        <div className="h-px bg-[#e4dfd8]" />

        {/* ── What to Watch ── */}
        <section className="py-8">
          <h3 className="text-xs font-bold text-[#c4523e] uppercase tracking-[0.15em] mb-5">
            Coming up
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {nextMeeting && (
              <div className="bg-white border border-[#e4dfd8] rounded-lg p-5">
                <p className="text-xs font-medium text-[#8a7e72] uppercase tracking-wide mb-2">Next meeting</p>
                <p className="text-lg font-bold text-[#1a2332]">{shortDate(nextMeeting.meeting_date)}</p>
                {nextMeeting.agenda_url && (
                  <a
                    href={nextMeeting.agenda_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-block mt-2 text-sm text-[#3d5a80] underline decoration-[#3d5a80]/30 underline-offset-2 hover:text-[#1a2332]"
                  >
                    View agenda
                  </a>
                )}
              </div>
            )}
            {upcomingElection && (() => {
              const year = upcomingElection.election_date.slice(0, 4)
              const slug = `${year}-${upcomingElection.election_type}`
              return (
                <div className="bg-[#1a2332] rounded-lg p-5">
                  <p className="text-xs font-medium text-[#7a8ba3] uppercase tracking-wide mb-2">Election</p>
                  <Link href={`/elections/${slug}`}>
                    <p className="text-lg font-bold text-white hover:text-[#a3bdd4] transition-colors">
                      {upcomingElection.election_name || `${year} ${upcomingElection.election_type}`}
                    </p>
                  </Link>
                  <p className="text-sm text-[#7a8ba3] mt-1">{shortDate(upcomingElection.election_date)}</p>
                </div>
              )
            })()}
          </div>
        </section>

        <div className="h-px bg-[#e4dfd8]" />

        {/* ── Active Issues ── */}
        <section className="py-8">
          <h3 className="text-xs font-bold text-[#c4523e] uppercase tracking-[0.15em] mb-5">
            Active issues
          </h3>
          <div className="flex flex-wrap gap-2">
            {activeTopics.map(topic => {
              const issue = issueMap.get(topic.topic_label)
              return (
                <Link
                  key={topic.topic_label}
                  href={`/topics/${topic.topic_label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/-+$/, '')}`}
                  className="group"
                >
                  <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium transition-all
                    ${issue ? issue.color : 'bg-slate-100 text-slate-700'}
                    group-hover:ring-2 group-hover:ring-offset-1 group-hover:ring-[#3d5a80]/20`}
                  >
                    {topic.topic_label}
                    <span className="text-xs opacity-60">{topic.item_count}</span>
                  </span>
                </Link>
              )
            })}
          </div>
        </section>

        <div className="h-px bg-[#e4dfd8]" />

        {/* ── Recent Meetings (compact) ── */}
        <section className="py-8">
          <h3 className="text-xs font-bold text-[#c4523e] uppercase tracking-[0.15em] mb-5">
            Recent meetings
          </h3>
          <div className="space-y-3">
            {meetings.slice(1, 6).map((m) => {
              const recap = m.meeting_recap || m.meeting_summary
              const oneLiner = recap
                ? recap.split('\n')[0].replace(/^[•\-]\s*/, '').replace(/\*\*([^*]+)\*\*/g, '$1').slice(0, 100)
                : null
              return (
                <Link
                  key={m.id}
                  href={`/meetings/${m.id}`}
                  className="flex gap-4 items-baseline group"
                >
                  <time
                    dateTime={m.meeting_date}
                    className="text-sm text-[#8a7e72] shrink-0 w-16 text-right tabular-nums"
                  >
                    {monthDay(m.meeting_date)}
                  </time>
                  <span className="text-[#1a2332] group-hover:text-[#3d5a80] transition-colors text-sm">
                    {oneLiner ? (oneLiner.length >= 100 ? oneLiner + '...' : oneLiner) : 'City council meeting'}
                  </span>
                </Link>
              )
            })}
          </div>
        </section>

        <div className="h-px bg-[#e4dfd8]" />

        {/* ── Council ── */}
        <section className="py-8">
          <h3 className="text-xs font-bold text-[#c4523e] uppercase tracking-[0.15em] mb-5">
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
                  <div className={`w-12 h-12 rounded-full mx-auto flex items-center justify-center text-sm font-bold
                    ${isMayor ? 'bg-[#1a2332] text-white' : 'bg-[#e4dfd8] text-[#5a5347]'}
                    group-hover:ring-2 group-hover:ring-[#3d5a80]/30 transition-all`}
                  >
                    {initials}
                  </div>
                  <p className="mt-2 text-sm font-medium text-[#1a2332] group-hover:text-[#3d5a80] transition-colors">
                    {o.name.split(' ').slice(-1)[0]}
                  </p>
                  {isMayor && (
                    <p className="text-xs text-[#8a7e72]">Mayor</p>
                  )}
                </Link>
              )
            })}
          </div>
        </section>

        {/* ── Footer ── */}
        <footer className="py-8 border-t border-[#e4dfd8] text-center">
          <Link href="/search" className="text-sm text-[#8a7e72] hover:text-[#3d5a80] transition-colors">
            Search all records
          </Link>
          <span className="mx-3 text-[#d1cbc3]">·</span>
          <Link href="/about" className="text-sm text-[#8a7e72] hover:text-[#3d5a80] transition-colors">
            About
          </Link>
          <p className="text-xs text-[#c1bab0] mt-3">
            From official city records · richmondcommons.org
          </p>
        </footer>
      </div>
    </div>
  )
}
