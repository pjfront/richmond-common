import Link from 'next/link'
import { getMeetingsWithCounts, getMostDiscussedItems, getOfficials, getUpcomingElection, getNextMeeting, getTopicCounts } from '@/lib/queries'

export const metadata = { title: 'Civic — Prototype' }

function shortDate(dateStr: string): string {
  return new Date(dateStr + 'T12:00:00').toLocaleDateString('en-US', {
    month: 'long', day: 'numeric',
  })
}

function daysUntil(dateStr: string): number {
  const target = new Date(dateStr + 'T12:00:00')
  const now = new Date()
  now.setHours(12, 0, 0, 0)
  return Math.ceil((target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
}

function recapLines(meeting: { meeting_recap?: string | null; meeting_summary?: string | null }): string[] {
  const source = meeting.meeting_recap || meeting.meeting_summary
  if (!source) return []
  return source.split('\n').filter(Boolean)
    .map(l => l.replace(/^[•\-]\s*/, '').replace(/\*\*([^*]+)\*\*/g, '$1').trim())
    .filter(l => l.length > 20)
    .slice(0, 3)
}

export default async function CivicPage() {
  const [meetings, discussed, officials, upcomingElection, nextMeeting, topicCounts] = await Promise.all([
    getMeetingsWithCounts(),
    getMostDiscussedItems(3, 120),
    getOfficials(undefined, { councilOnly: true, currentOnly: true }),
    getUpcomingElection(),
    getNextMeeting(),
    getTopicCounts(),
  ])

  const latest = meetings[0]
  const recap = latest ? recapLines(latest) : []

  const electionDays = upcomingElection ? daysUntil(upcomingElection.election_date) : null
  const meetingDays = nextMeeting ? daysUntil(nextMeeting.meeting_date) : null

  const topTopics = topicCounts.slice(0, 5)

  return (
    <div className="min-h-screen bg-white">

      {/* ── Hero ── */}
      <header className="bg-[#1b4965] text-white">
        <div className="max-w-3xl mx-auto px-6 pt-6 pb-12">
          <div className="flex items-center justify-between mb-10">
            <Link href="/prototype" className="text-white/40 text-xs tracking-widest uppercase hover:text-white/60 transition-colors">
              Prototype
            </Link>
            <Link href="/search" className="text-sm text-white/50 hover:text-white/80 transition-colors">
              Search &rarr;
            </Link>
          </div>
          <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight leading-[1.1]">
            What&apos;s happening in<br />
            <span className="text-[#bee9e8]">Richmond</span> government
          </h1>
          <p className="mt-4 text-lg text-white/60 max-w-md">
            Council votes, public testimony, and campaign money — from official records, in plain language.
          </p>
        </div>
      </header>

      {/* ── Countdown strip ── */}
      <div className="bg-[#f0f7f4] border-b border-[#d1e8df]">
        <div className="max-w-3xl mx-auto px-6 py-4 flex flex-wrap gap-6">
          {nextMeeting && meetingDays !== null && meetingDays > 0 && (
            <div className="flex items-center gap-3">
              <span className="text-3xl font-extrabold text-[#1b4965]">{meetingDays}</span>
              <div>
                <p className="text-xs font-medium text-[#1b4965]/60 uppercase tracking-wide">days to</p>
                <p className="text-sm font-semibold text-[#1b4965]">Next council meeting</p>
              </div>
            </div>
          )}
          {upcomingElection && electionDays !== null && electionDays > 0 && (
            <div className="flex items-center gap-3">
              <span className="text-3xl font-extrabold text-[#c4523e]">{electionDays}</span>
              <div>
                <p className="text-xs font-medium text-[#c4523e]/60 uppercase tracking-wide">days to</p>
                <Link href={`/elections/${upcomingElection.election_date.slice(0, 4)}-${upcomingElection.election_type}`}>
                  <p className="text-sm font-semibold text-[#c4523e] hover:text-[#a03d2e] transition-colors">
                    {upcomingElection.election_name || 'Election'}
                  </p>
                </Link>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-6">

        {/* ── Latest Meeting ── */}
        {latest && (
          <section className="py-10">
            <p className="text-xs font-bold text-[#1b4965]/40 uppercase tracking-[0.15em] mb-3">
              Latest from City Hall
            </p>
            <Link href={`/meetings/${latest.id}`}>
              <h2 className="text-2xl sm:text-3xl font-bold text-[#1a2332] leading-tight hover:text-[#1b4965] transition-colors">
                {recap[0] || `Council met ${shortDate(latest.meeting_date)}`}
              </h2>
            </Link>
            {recap.length > 1 && (
              <ul className="mt-4 space-y-2">
                {recap.slice(1).map((line, i) => (
                  <li key={i} className="flex items-start gap-2 text-[#475569]">
                    <span className="text-[#bee9e8] mt-1">&#9656;</span>
                    <span>{line}</span>
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-4 flex gap-4 text-sm">
              {latest.minutes_url && (
                <a href={latest.minutes_url} target="_blank" rel="noopener noreferrer"
                  className="text-[#1b4965]/50 hover:text-[#1b4965] underline decoration-[#1b4965]/20 underline-offset-2 transition-colors">
                  Minutes
                </a>
              )}
              {latest.agenda_url && (
                <a href={latest.agenda_url} target="_blank" rel="noopener noreferrer"
                  className="text-[#1b4965]/50 hover:text-[#1b4965] underline decoration-[#1b4965]/20 underline-offset-2 transition-colors">
                  Agenda
                </a>
              )}
            </div>
          </section>
        )}

        {/* ── Community Voice ── */}
        {discussed.length > 0 && (
          <section className="py-8 border-t border-[#e8e4df]">
            <p className="text-xs font-bold text-[#c4523e] uppercase tracking-[0.15em] mb-5">
              People showed up for
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {discussed.map((item) => (
                <Link
                  key={item.agenda_item_id}
                  href={`/meetings/${item.meeting_id}/items/${item.agenda_item_id}`}
                  className="group block bg-[#faf8f5] rounded-lg p-4 hover:bg-[#f0eee9] transition-colors"
                >
                  <p className="text-3xl font-extrabold text-[#1b4965]">{item.public_comment_count}</p>
                  <p className="text-xs text-[#8a7e72] mt-0.5 mb-2">public speakers</p>
                  <p className="text-sm font-medium text-[#1a2332] leading-snug group-hover:text-[#1b4965] transition-colors">
                    {(item.summary_headline || item.title).slice(0, 80)}
                    {(item.summary_headline || item.title).length > 80 ? '...' : ''}
                  </p>
                </Link>
              ))}
            </div>
          </section>
        )}

        {/* ── Issues strip ── */}
        <section className="py-8 border-t border-[#e8e4df]">
          <p className="text-xs font-bold text-[#1b4965]/40 uppercase tracking-[0.15em] mb-4">
            Issues the council keeps coming back to
          </p>
          <div className="flex flex-wrap gap-2">
            {topTopics.map(topic => (
              <Link
                key={topic.topic_label}
                href={`/topics/${topic.topic_label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/-+$/, '')}`}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full bg-[#1b4965] text-white text-sm font-medium hover:bg-[#16384e] transition-colors"
              >
                {topic.topic_label}
              </Link>
            ))}
          </div>
        </section>

        {/* ── Your Council ── */}
        <section className="py-8 border-t border-[#e8e4df]">
          <p className="text-xs font-bold text-[#1b4965]/40 uppercase tracking-[0.15em] mb-5">
            Your council
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {officials.filter(o => o.is_current).map((o) => {
              const slug = o.name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '')
              const isMayor = o.role === 'mayor'
              const isViceMayor = o.role === 'vice_mayor'
              return (
                <Link
                  key={o.id}
                  href={`/council/${slug}`}
                  className={`group flex items-center gap-3 rounded-lg p-3 transition-colors
                    ${isMayor ? 'bg-[#1b4965] text-white hover:bg-[#16384e]' : 'bg-[#faf8f5] hover:bg-[#f0eee9]'}`}
                >
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold shrink-0
                    ${isMayor ? 'bg-white/20 text-white' : 'bg-[#1b4965]/10 text-[#1b4965]'}`}
                  >
                    {o.name.split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase()}
                  </div>
                  <div>
                    <p className={`font-semibold text-sm ${isMayor ? 'text-white' : 'text-[#1a2332] group-hover:text-[#1b4965]'} transition-colors`}>
                      {o.name}
                    </p>
                    {(isMayor || isViceMayor) && (
                      <p className={`text-xs ${isMayor ? 'text-white/60' : 'text-[#8a7e72]'}`}>
                        {isMayor ? 'Mayor' : 'Vice Mayor'}
                      </p>
                    )}
                  </div>
                </Link>
              )
            })}
          </div>
        </section>

        {/* ── Quick links ── */}
        <section className="py-8 border-t border-[#e8e4df]">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { href: '/meetings', label: 'All meetings', desc: 'By date' },
              { href: '/elections', label: 'Elections', desc: 'Candidates & money' },
              { href: '/search', label: 'Search', desc: 'Find anything' },
              { href: '/about', label: 'About', desc: 'How this works' },
            ].map(link => (
              <Link
                key={link.href}
                href={link.href}
                className="group block text-center rounded-lg border border-[#e8e4df] p-4 hover:border-[#1b4965]/30 hover:bg-[#f0f7f4] transition-all"
              >
                <p className="text-sm font-semibold text-[#1a2332] group-hover:text-[#1b4965] transition-colors">{link.label}</p>
                <p className="text-xs text-[#8a7e72] mt-0.5">{link.desc}</p>
              </Link>
            ))}
          </div>
        </section>

        {/* ── Footer ── */}
        <footer className="py-8 border-t border-[#e8e4df] text-center">
          <p className="text-xs text-[#c1bab0]">
            From official city records · richmondcommons.org
          </p>
        </footer>
      </div>
    </div>
  )
}
