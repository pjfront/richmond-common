import Link from 'next/link'
import { notFound } from 'next/navigation'
import { getMeeting, getAdjacentMeetings } from '@/lib/queries'

export const metadata = { title: 'Meeting — The Record' }

const serif = { fontFamily: 'Georgia, "Times New Roman", serif' }
const sans = { fontFamily: 'Inter, system-ui, sans-serif' }

function fullDate(dateStr: string): string {
  return new Date(dateStr + 'T12:00:00').toLocaleDateString('en-US', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
  })
}

function tinyDate(dateStr: string): string {
  return new Date(dateStr + 'T12:00:00').toLocaleDateString('en-US', {
    month: 'short', day: 'numeric',
  })
}

/** Summarize a vote: "Passed 5-2" or "Failed 3-4" */
function describeVote(result: string, tally: string | null): string {
  if (!tally) return result
  const ayeMatch = tally.match(/(?:Ayes?)\s*\((\d+)\)/i)
  const nayMatch = tally.match(/(?:Noes?|Nays?)\s*\((\d+)\)/i)
  if (ayeMatch && nayMatch) {
    const label = result.toLowerCase().includes('pass') || result.toLowerCase().includes('adopt') ? 'Passed' : result.toLowerCase().includes('fail') ? 'Failed' : result
    return `${label} ${ayeMatch[1]}–${nayMatch[1]}`
  }
  return result
}

/** Who voted no? */
function dissent(votes: Array<{ vote_choice: string; official_name: string }>): string[] {
  return votes
    .filter(v => v.vote_choice.toLowerCase() === 'nay' || v.vote_choice.toLowerCase() === 'no')
    .map(v => v.official_name)
}

export default async function RecordMeetingPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  const meeting = await getMeeting(id)
  if (!meeting) notFound()

  const adjacent = await getAdjacentMeetings(meeting.meeting_date, meeting.body_id, meeting.meeting_type)

  // Extract the narrative
  const recapText = meeting.meeting_recap || meeting.transcript_recap || null
  const summaryBullets = meeting.meeting_summary
    ? meeting.meeting_summary.split('\n').filter(Boolean).map(b => b.replace(/^[•\-]\s*/, '').trim())
    : []

  // Separate non-consent items (the real business) from consent calendar
  const substantive = meeting.agenda_items.filter(i => !i.is_consent_calendar)
  const consent = meeting.agenda_items.filter(i => i.is_consent_calendar)

  // Find items with votes (the interesting ones)
  const votedItems = substantive.filter(i => i.motions.some(m => m.votes.length > 0))

  // Find split votes (the most interesting ones)
  const splitVoteItems = votedItems.filter(i =>
    i.motions.some(m => {
      const nays = m.votes.filter(v => v.vote_choice.toLowerCase() === 'nay' || v.vote_choice.toLowerCase() === 'no')
      return nays.length > 0
    })
  )

  // Find items with public comments
  const commentedItems = substantive.filter(i => (i.public_comment_count ?? 0) > 0)

  // Who attended?
  const present = meeting.attendance.filter(a => a.status === 'present')
  const absent = meeting.attendance.filter(a => a.status === 'absent')

  return (
    <div className="max-w-[640px] mx-auto px-5 pb-20" style={serif}>

      {/* ── Header ── */}
      <header className="pt-12 pb-8 border-b border-neutral-200">
        <p className="text-sm text-neutral-400 mb-2" style={sans}>
          City Council Meeting
        </p>
        <h1 className="text-3xl font-bold text-neutral-900 leading-tight">
          {fullDate(meeting.meeting_date)}
        </h1>
        {meeting.presiding_officer && (
          <p className="text-neutral-500 mt-2">
            Presided by {meeting.presiding_officer}
          </p>
        )}
      </header>

      {/* ── The Story ── */}
      {recapText && (
        <article className="pt-8 pb-8 border-b border-neutral-100">
          <h2 className="text-xs font-medium text-neutral-400 uppercase tracking-widest mb-4" style={sans}>
            What happened
          </h2>
          <div className="space-y-4 text-[17px] text-neutral-700 leading-relaxed">
            {recapText.split('\n\n').filter(Boolean).map((para, i) => (
              <p key={i}>
                {para.split(/(\*\*[^*]+\*\*)/).map((chunk, j) =>
                  chunk.startsWith('**') && chunk.endsWith('**')
                    ? <strong key={j} className="font-semibold text-neutral-900">{chunk.slice(2, -2)}</strong>
                    : chunk
                )}
              </p>
            ))}
          </div>
          {meeting.minutes_url && (
            <p className="mt-5 text-sm text-neutral-400" style={sans}>
              Summarized from the{' '}
              <a href={meeting.minutes_url} target="_blank" rel="noopener noreferrer"
                className="text-neutral-500 underline decoration-neutral-300 hover:text-neutral-700">
                official minutes
              </a>
            </p>
          )}
        </article>
      )}

      {/* ── Fallback: summary bullets if no recap ── */}
      {!recapText && summaryBullets.length > 0 && (
        <article className="pt-8 pb-8 border-b border-neutral-100">
          <h2 className="text-xs font-medium text-neutral-400 uppercase tracking-widest mb-4" style={sans}>
            What happened
          </h2>
          <div className="space-y-3 text-[17px] text-neutral-700 leading-relaxed">
            {summaryBullets.map((bullet, i) => (
              <p key={i}>{bullet}</p>
            ))}
          </div>
        </article>
      )}

      {/* ── Split votes — the real news ── */}
      {splitVoteItems.length > 0 && (
        <section className="pt-8 pb-8 border-b border-neutral-100">
          <h2 className="text-xs font-medium text-neutral-400 uppercase tracking-widest mb-5" style={sans}>
            {splitVoteItems.length === 1 ? 'Contested vote' : 'Contested votes'}
          </h2>
          <div className="space-y-6">
            {splitVoteItems.map((item) => {
              const motion = item.motions.find(m => m.votes.length > 0)
              if (!motion) return null
              const dissenters = dissent(motion.votes)
              return (
                <div key={item.id}>
                  <p className="text-[17px] text-neutral-800 leading-snug">
                    {item.plain_language_summary || item.summary_headline || item.title}
                  </p>
                  <p className="text-sm text-neutral-400 mt-1" style={sans}>
                    {describeVote(motion.result, motion.vote_tally)}
                    {dissenters.length > 0 && (
                      <> · {dissenters.join(', ')} voted no</>
                    )}
                  </p>
                  {(item.public_comment_count ?? 0) > 0 && (
                    <p className="text-sm text-neutral-400 mt-0.5" style={sans}>
                      {item.public_comment_count} public {item.public_comment_count === 1 ? 'comment' : 'comments'}
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* ── What people said ── */}
      {commentedItems.length > 0 && (
        <section className="pt-8 pb-8 border-b border-neutral-100">
          <h2 className="text-xs font-medium text-neutral-400 uppercase tracking-widest mb-5" style={sans}>
            Public testimony
          </h2>
          <div className="space-y-4">
            {commentedItems.slice(0, 5).map((item) => {
              // Show theme narratives if available
              const themes = item.theme_narratives?.slice(0, 2)
              return (
                <div key={item.id}>
                  <p className="text-[17px] text-neutral-800 leading-snug">
                    {item.summary_headline || item.title}
                  </p>
                  {themes && themes.length > 0 ? (
                    <div className="mt-1.5 space-y-1">
                      {themes.map((t, i) => (
                        <p key={i} className="text-sm text-neutral-500 leading-relaxed" style={sans}>
                          {t.narrative.slice(0, 200)}{t.narrative.length > 200 ? '...' : ''}
                        </p>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-neutral-400 mt-1" style={sans}>
                      {item.public_comment_count} {item.public_comment_count === 1 ? 'person' : 'people'} commented
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* ── Everything else (compact feed) ── */}
      {substantive.filter(i => !splitVoteItems.includes(i) && !commentedItems.includes(i)).length > 0 && (
        <section className="pt-8 pb-8 border-b border-neutral-100">
          <h2 className="text-xs font-medium text-neutral-400 uppercase tracking-widest mb-5" style={sans}>
            Also on the agenda
          </h2>
          <div className="space-y-2">
            {substantive
              .filter(i => !splitVoteItems.includes(i) && !commentedItems.includes(i))
              .slice(0, 10)
              .map((item) => {
                const motion = item.motions.find(m => m.result)
                return (
                  <p key={item.id} className="text-sm text-neutral-600" style={sans}>
                    {item.summary_headline || item.title}
                    {motion && (
                      <span className="text-neutral-400"> · {motion.result.toLowerCase()}</span>
                    )}
                  </p>
                )
              })}
            {substantive.filter(i => !splitVoteItems.includes(i) && !commentedItems.includes(i)).length > 10 && (
              <p className="text-sm text-neutral-400">
                and {substantive.filter(i => !splitVoteItems.includes(i) && !commentedItems.includes(i)).length - 10} more items
              </p>
            )}
          </div>
        </section>
      )}

      {/* ── Consent calendar ── */}
      {consent.length > 0 && (
        <section className="pt-8 pb-8 border-b border-neutral-100">
          <h2 className="text-xs font-medium text-neutral-400 uppercase tracking-widest mb-3" style={sans}>
            Passed without debate
          </h2>
          <p className="text-sm text-neutral-500" style={sans}>
            {consent.length} routine {consent.length === 1 ? 'item' : 'items'} approved on the consent calendar.
          </p>
        </section>
      )}

      {/* ── Attendance ── */}
      {present.length > 0 && (
        <section className="pt-8 pb-8 border-b border-neutral-100">
          <h2 className="text-xs font-medium text-neutral-400 uppercase tracking-widest mb-3" style={sans}>
            Who was there
          </h2>
          <p className="text-neutral-600 text-sm" style={sans}>
            {present.map(a => a.official.name).join(', ')}
            {absent.length > 0 && (
              <span className="text-neutral-400">
                {' · Absent: '}{absent.map(a => a.official.name).join(', ')}
              </span>
            )}
          </p>
        </section>
      )}

      {/* ── Source links ── */}
      <section className="pt-8 pb-8 border-b border-neutral-100">
        <div className="flex gap-6 text-sm text-neutral-400" style={sans}>
          {meeting.minutes_url && (
            <a href={meeting.minutes_url} target="_blank" rel="noopener noreferrer"
              className="underline decoration-neutral-300 hover:text-neutral-600">
              Official minutes
            </a>
          )}
          {meeting.agenda_url && (
            <a href={meeting.agenda_url} target="_blank" rel="noopener noreferrer"
              className="underline decoration-neutral-300 hover:text-neutral-600">
              Full agenda packet
            </a>
          )}
          <Link href={`/meetings/${meeting.id}`}
            className="underline decoration-neutral-300 hover:text-neutral-600">
            Full detail view
          </Link>
        </div>
      </section>

      {/* ── Navigation ── */}
      <nav className="pt-8 pb-8 flex justify-between text-sm" style={sans}>
        {adjacent.previous ? (
          <Link href={`/prototype/record/meeting/${adjacent.previous.id}`}
            className="text-neutral-400 hover:text-neutral-600">
            &larr; {tinyDate(adjacent.previous.meeting_date)}
          </Link>
        ) : <span />}
        <Link href="/prototype/record" className="text-neutral-400 hover:text-neutral-600">
          Home
        </Link>
        {adjacent.next ? (
          <Link href={`/prototype/record/meeting/${adjacent.next.id}`}
            className="text-neutral-400 hover:text-neutral-600">
            {tinyDate(adjacent.next.meeting_date)} &rarr;
          </Link>
        ) : <span />}
      </nav>
    </div>
  )
}
