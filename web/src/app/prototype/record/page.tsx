import Link from 'next/link'
import { getMeetingsWithCounts, getMostDiscussedItems, getControversialItems, getOfficials, getNextMeeting, getUpcomingElection } from '@/lib/queries'

export const metadata = { title: 'The Record — Prototype' }

/** Format as "Tuesday, April 8" */
function shortDate(dateStr: string): string {
  return new Date(dateStr + 'T12:00:00').toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric',
  })
}

/** Format as "Apr 8" */
function tinyDate(dateStr: string): string {
  return new Date(dateStr + 'T12:00:00').toLocaleDateString('en-US', {
    month: 'short', day: 'numeric',
  })
}

/** Turn meeting_summary bullets or meeting_recap into clean prose paragraphs */
function narrativeFromMeeting(meeting: { meeting_recap?: string | null; meeting_summary?: string | null }): string[] {
  // Prefer recap (full narrative paragraphs)
  if (meeting.meeting_recap) {
    return meeting.meeting_recap
      .split('\n\n')
      .filter(Boolean)
      .map(p => p.replace(/\*\*([^*]+)\*\*/g, '$1')) // strip markdown bold for now
      .slice(0, 3) // max 3 paragraphs
  }
  // Fall back to summary bullets, joined into prose
  if (meeting.meeting_summary) {
    const bullets = meeting.meeting_summary
      .split('\n')
      .filter(Boolean)
      .map(b => b.replace(/^[•\-]\s*/, '').trim())
      .slice(0, 4)
    if (bullets.length > 0) return [bullets.join('. ') + '.']
  }
  return []
}

/** Parse "Ayes: 5, Noes: 2" style tally */
function describeTally(tally: string | null): string {
  if (!tally) return ''
  const ayeMatch = tally.match(/(?:Ayes?|Yes)\s*(?:\((\d+)\)|:\s*(\d+))/i)
  const nayMatch = tally.match(/(?:Noes?|Nays?|No)\s*(?:\((\d+)\)|:\s*(\d+))/i)
  const ayes = ayeMatch ? parseInt(ayeMatch[1] || ayeMatch[2]) : null
  const nays = nayMatch ? parseInt(nayMatch[1] || nayMatch[2]) : null
  if (ayes !== null && nays !== null) return `${ayes}–${nays}`
  return ''
}

const serif = { fontFamily: 'Georgia, "Times New Roman", serif' }

export default async function RecordHome() {
  const [meetings, discussed, controversial, officials, nextMeeting, upcomingElection] = await Promise.all([
    getMeetingsWithCounts(),
    getMostDiscussedItems(3, 120),
    getControversialItems(5),
    getOfficials(undefined, { councilOnly: true, currentOnly: true }),
    getNextMeeting(),
    getUpcomingElection(),
  ])

  const latest = meetings[0]
  const narrative = latest ? narrativeFromMeeting(latest) : []
  const recentMeetings = meetings.slice(1, 6)

  // Pick the top controversial item that isn't from the latest meeting
  const topContested = controversial.find(c => c.meeting_id !== latest?.id) ?? controversial[0]

  return (
    <div className="max-w-[640px] mx-auto px-5 pb-20" style={serif}>

      {/* ── Masthead ── */}
      <header className="pt-12 pb-10 border-b border-neutral-200">
        <h1 className="text-4xl font-bold tracking-tight text-neutral-900">
          Richmond Commons
        </h1>
        <p className="text-lg text-neutral-400 mt-1">
          What your city government is doing, in plain language.
        </p>
      </header>

      {/* ── Lead Story ── */}
      {latest && (
        <article className="pt-10 pb-10 border-b border-neutral-100">
          <p className="text-sm text-neutral-400 mb-3 tracking-wide" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
            <time dateTime={latest.meeting_date}>{shortDate(latest.meeting_date)}</time>
            {' · City Council'}
          </p>
          <Link href={`/prototype/record/meeting/${latest.id}`}>
            <h2 className="text-2xl font-bold text-neutral-900 leading-snug hover:text-neutral-600 transition-colors">
              {narrative.length > 0
                ? truncateToHeadline(narrative[0])
                : `The council met ${shortDate(latest.meeting_date)}`
              }
            </h2>
          </Link>
          {narrative.length > 1 && (
            <div className="mt-4 space-y-3 text-[17px] text-neutral-700 leading-relaxed">
              {narrative.slice(1, 3).map((para, i) => (
                <p key={i}>{para}</p>
              ))}
            </div>
          )}
          {latest.minutes_url && (
            <p className="mt-4 text-sm text-neutral-400" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
              From the{' '}
              <a href={latest.minutes_url} target="_blank" rel="noopener noreferrer" className="text-neutral-500 underline decoration-neutral-300 hover:text-neutral-700">
                official minutes
              </a>
            </p>
          )}
        </article>
      )}

      {/* ── What people are talking about ── */}
      {discussed.length > 0 && (
        <section className="pt-8 pb-8 border-b border-neutral-100">
          <h3 className="text-xs font-medium text-neutral-400 uppercase tracking-widest mb-5" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
            People showed up to talk about
          </h3>
          <div className="space-y-4">
            {discussed.map((item) => (
              <div key={item.agenda_item_id}>
                <Link
                  href={`/meetings/${item.meeting_id}/items/${item.agenda_item_id}`}
                  className="text-[17px] text-neutral-800 hover:text-neutral-600 transition-colors leading-snug"
                >
                  {item.summary_headline || item.title}
                </Link>
                <p className="text-sm text-neutral-400 mt-0.5" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
                  {item.public_comment_count} people commented · {tinyDate(item.meeting_date)}
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Contested votes ── */}
      {topContested && (
        <section className="pt-8 pb-8 border-b border-neutral-100">
          <h3 className="text-xs font-medium text-neutral-400 uppercase tracking-widest mb-5" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
            Split vote
          </h3>
          <Link
            href={`/meetings/${topContested.meeting_id}`}
            className="text-[17px] text-neutral-800 hover:text-neutral-600 transition-colors leading-snug"
          >
            {topContested.title}
          </Link>
          <p className="text-sm text-neutral-400 mt-1" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
            {topContested.result}
            {describeTally(topContested.vote_tally) && `, ${describeTally(topContested.vote_tally)}`}
            {' · '}{tinyDate(topContested.meeting_date)}
          </p>
        </section>
      )}

      {/* ── Recent feed ── */}
      {recentMeetings.length > 0 && (
        <section className="pt-8 pb-8 border-b border-neutral-100">
          <h3 className="text-xs font-medium text-neutral-400 uppercase tracking-widest mb-5" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
            Recent meetings
          </h3>
          <div className="space-y-3">
            {recentMeetings.map((m) => {
              const recap = m.meeting_recap || m.meeting_summary
              const oneLiner = recap
                ? recap.split('\n')[0].replace(/^[•\-]\s*/, '').replace(/\*\*([^*]+)\*\*/g, '$1').slice(0, 120)
                : null
              return (
                <div key={m.id} className="flex gap-4 items-baseline">
                  <time
                    dateTime={m.meeting_date}
                    className="text-sm text-neutral-400 shrink-0 w-14 text-right tabular-nums"
                    style={{ fontFamily: 'Inter, system-ui, sans-serif' }}
                  >
                    {tinyDate(m.meeting_date)}
                  </time>
                  <div className="min-w-0">
                    <Link
                      href={`/prototype/record/meeting/${m.id}`}
                      className="text-neutral-800 hover:text-neutral-500 transition-colors"
                    >
                      {oneLiner
                        ? oneLiner + (oneLiner.length >= 120 ? '...' : '')
                        : `City council meeting`
                      }
                    </Link>
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* ── What to watch ── */}
      <section className="pt-8 pb-8 border-b border-neutral-100">
        <h3 className="text-xs font-medium text-neutral-400 uppercase tracking-widest mb-5" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
          Coming up
        </h3>
        <div className="space-y-3">
          {nextMeeting && (
            <p className="text-[17px] text-neutral-700">
              Next council meeting: <span className="text-neutral-900 font-medium">{shortDate(nextMeeting.meeting_date)}</span>
              {nextMeeting.agenda_url && (
                <>
                  {' · '}
                  <a href={nextMeeting.agenda_url} target="_blank" rel="noopener noreferrer" className="text-neutral-500 underline decoration-neutral-300 hover:text-neutral-700">
                    agenda
                  </a>
                </>
              )}
            </p>
          )}
          {upcomingElection && (() => {
            const year = upcomingElection.election_date.slice(0, 4)
            const slug = `${year}-${upcomingElection.election_type}`
            return (
              <p className="text-[17px] text-neutral-700">
                <Link href={`/elections/${slug}`} className="text-neutral-900 font-medium hover:text-neutral-600">
                  {upcomingElection.election_name || `${year} ${upcomingElection.election_type}`}
                </Link>
                {' · '}{shortDate(upcomingElection.election_date)}
              </p>
            )
          })()}
        </div>
      </section>

      {/* ── Council ── */}
      <section className="pt-8 pb-8 border-b border-neutral-100">
        <h3 className="text-xs font-medium text-neutral-400 uppercase tracking-widest mb-5" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
          Your council
        </h3>
        <div className="space-y-1.5">
          {officials.filter(o => o.is_current).map((o) => {
            const slug = o.name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '')
            const role = o.role === 'mayor' ? 'Mayor' : o.role === 'vice_mayor' ? 'Vice Mayor' : null
            return (
              <p key={o.id} className="text-[17px]">
                <Link href={`/prototype/record/council/${slug}`} className="text-neutral-800 hover:text-neutral-500 transition-colors">
                  {o.name}
                </Link>
                {role && <span className="text-neutral-400 ml-1.5">{role}</span>}
              </p>
            )
          })}
        </div>
      </section>

      {/* ── Search ── */}
      <section className="pt-8 pb-8">
        <Link
          href="/search"
          className="block text-center text-neutral-400 hover:text-neutral-600 transition-colors text-sm py-3 border border-neutral-200 rounded"
          style={{ fontFamily: 'Inter, system-ui, sans-serif' }}
        >
          Search Richmond Commons
        </Link>
      </section>

    </div>
  )
}

/** Extract a good headline from the first paragraph of a recap */
function truncateToHeadline(text: string): string {
  // Take first sentence or first 140 chars, whichever is shorter
  const firstSentence = text.match(/^[^.!?]+[.!?]/)
  if (firstSentence && firstSentence[0].length <= 140) {
    return firstSentence[0]
  }
  if (text.length <= 140) return text
  return text.slice(0, 137) + '...'
}
