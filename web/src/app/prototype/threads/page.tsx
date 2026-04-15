import Link from 'next/link'
import { getTopicCounts, getTopicItems, getMostDiscussedItems, getNextMeeting, getTopicTaxonomy } from '@/lib/queries'

export const metadata = { title: 'Threads — Prototype' }

function monthDay(dateStr: string): string {
  return new Date(dateStr + 'T12:00:00').toLocaleDateString('en-US', {
    month: 'short', day: 'numeric',
  })
}

function shortDate(dateStr: string): string {
  return new Date(dateStr + 'T12:00:00').toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric',
  })
}

// Color palette for threads — earthy, warm, distinct
const THREAD_COLORS = [
  { bg: '#2d4a3e', text: '#a8d4b8', accent: '#5cb87a', dot: '#5cb87a' },
  { bg: '#3d2b4a', text: '#c4a8d4', accent: '#9b6bb5', dot: '#9b6bb5' },
  { bg: '#4a3b2d', text: '#d4c4a8', accent: '#c49b5c', dot: '#c49b5c' },
  { bg: '#2d3d4a', text: '#a8c4d4', accent: '#5c9bc4', dot: '#5c9bc4' },
  { bg: '#4a2d2d', text: '#d4a8a8', accent: '#c45c5c', dot: '#c45c5c' },
]

export default async function ThreadsPage() {
  const [topicCounts, discussed, nextMeeting, richmondLocalIssues] = await Promise.all([
    getTopicCounts(),
    getMostDiscussedItems(10, 180),
    getNextMeeting(),
    getTopicTaxonomy(),
  ])

  // Pick top 4 topics that have recent activity and are interesting local issues
  const issueLabels = new Set(richmondLocalIssues.map(i => i.label))
  const activeTopics = topicCounts
    .filter(t => issueLabels.has(t.topic_label))
    .slice(0, 4)

  // Fetch recent items for each topic
  const threadData = await Promise.all(
    activeTopics.map(async (topic, i) => {
      const items = await getTopicItems(topic.topic_label, 5)
      const issue = richmondLocalIssues.find(iss => iss.label === topic.topic_label)
      return {
        topic,
        issue,
        items,
        color: THREAD_COLORS[i % THREAD_COLORS.length],
      }
    })
  )

  // Remaining topics for the "more" section
  const shownLabels = new Set(activeTopics.map(t => t.topic_label))
  const moreTopics = topicCounts.filter(t => !shownLabels.has(t.topic_label)).slice(0, 8)

  return (
    <div className="min-h-screen bg-[#0f1419]">

      {/* ── Header ── */}
      <header className="border-b border-white/10">
        <div className="max-w-3xl mx-auto px-6 py-5 flex items-end justify-between">
          <div>
            <Link href="/prototype" className="text-white/30 text-xs tracking-widest uppercase hover:text-white/50 transition-colors">
              Prototype
            </Link>
            <h1 className="text-2xl font-bold text-white tracking-tight mt-0.5">
              Richmond Commons
            </h1>
          </div>
          <p className="text-white/30 text-sm hidden sm:block">
            Follow the threads
          </p>
        </div>
      </header>

      <div className="max-w-3xl mx-auto px-6">

        {/* ── Intro ── */}
        <div className="pt-10 pb-8">
          <p className="text-xl text-white/60 leading-relaxed max-w-lg">
            Richmond politics is a set of ongoing stories.
            <br />
            <span className="text-white/90 font-medium">Pick a thread and follow it.</span>
          </p>
        </div>

        {/* ── Threads ── */}
        <div className="space-y-6 pb-8">
          {threadData.map(({ topic, issue, items, color }) => (
            <article
              key={topic.topic_label}
              className="rounded-xl overflow-hidden"
              style={{ backgroundColor: color.bg }}
            >
              {/* Thread header */}
              <div className="px-6 pt-6 pb-4">
                <div className="flex items-start justify-between">
                  <div>
                    <h2 className="text-xl font-bold" style={{ color: '#fff' }}>
                      {topic.topic_label}
                    </h2>
                    {issue && (
                      <p className="text-sm mt-1 leading-relaxed max-w-md" style={{ color: color.text }}>
                        {issue.context}
                      </p>
                    )}
                  </div>
                  <span className="text-xs font-medium px-2 py-1 rounded-full bg-white/10" style={{ color: color.accent }}>
                    {topic.item_count} items
                  </span>
                </div>
              </div>

              {/* Timeline */}
              <div className="px-6 pb-6">
                <div className="relative">
                  {/* Timeline line */}
                  <div
                    className="absolute left-[5px] top-2 bottom-2 w-px"
                    style={{ backgroundColor: color.accent + '40' }}
                  />

                  <div className="space-y-3">
                    {items.slice(0, 4).map((item) => (
                      <Link
                        key={item.id}
                        href={`/meetings/${item.meeting_id}/items/${item.id}`}
                        className="block group"
                      >
                        <div className="flex items-start gap-3 pl-0">
                          {/* Dot */}
                          <div
                            className="w-[11px] h-[11px] rounded-full shrink-0 mt-1.5"
                            style={{ backgroundColor: color.dot }}
                          />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-white/90 leading-snug group-hover:text-white transition-colors">
                              {item.summary_headline || (item.title.length > 90 ? item.title.slice(0, 87) + '...' : item.title)}
                            </p>
                            <div className="flex items-center gap-2 mt-0.5">
                              <time className="text-xs" style={{ color: color.text }}>
                                {monthDay(item.meeting_date)}
                              </time>
                              {item.public_comment_count > 0 && (
                                <span className="text-xs" style={{ color: color.accent }}>
                                  {item.public_comment_count} speakers
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </Link>
                    ))}
                  </div>
                </div>

                {/* Follow link */}
                <Link
                  href={`/topics/${topic.topic_label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/-+$/, '')}`}
                  className="inline-block mt-4 text-sm font-medium transition-colors"
                  style={{ color: color.accent }}
                >
                  Full thread &rarr;
                </Link>
              </div>
            </article>
          ))}
        </div>

        {/* ── More threads ── */}
        {moreTopics.length > 0 && (
          <section className="py-8 border-t border-white/10">
            <h3 className="text-xs font-bold text-white/30 uppercase tracking-[0.15em] mb-4">
              More threads
            </h3>
            <div className="flex flex-wrap gap-2">
              {moreTopics.map(topic => (
                <Link
                  key={topic.topic_label}
                  href={`/topics/${topic.topic_label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/-+$/, '')}`}
                  className="text-sm px-3 py-1.5 rounded-full bg-white/5 text-white/50 hover:bg-white/10 hover:text-white/70 transition-all"
                >
                  {topic.topic_label}
                </Link>
              ))}
            </div>
          </section>
        )}

        {/* ── What's Happening ── */}
        <section className="py-8 border-t border-white/10">
          <h3 className="text-xs font-bold text-white/30 uppercase tracking-[0.15em] mb-4">
            People are talking about
          </h3>
          <div className="space-y-3">
            {discussed.slice(0, 4).map((item) => (
              <Link
                key={item.agenda_item_id}
                href={`/meetings/${item.meeting_id}/items/${item.agenda_item_id}`}
                className="flex items-baseline gap-3 group"
              >
                <span className="text-sm text-white/30 shrink-0 w-16 text-right tabular-nums">
                  {item.public_comment_count} spoke
                </span>
                <span className="text-sm text-white/70 group-hover:text-white transition-colors">
                  {item.summary_headline || item.title}
                </span>
              </Link>
            ))}
          </div>
        </section>

        {/* ── Coming up ── */}
        {nextMeeting && (
          <section className="py-8 border-t border-white/10">
            <div className="bg-white/5 rounded-lg p-5">
              <p className="text-xs font-bold text-white/30 uppercase tracking-[0.15em] mb-2">Next council meeting</p>
              <p className="text-lg font-bold text-white">{shortDate(nextMeeting.meeting_date)}</p>
              {nextMeeting.agenda_url && (
                <a
                  href={nextMeeting.agenda_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-block mt-2 text-sm text-white/50 hover:text-white/80 transition-colors underline decoration-white/20 underline-offset-2"
                >
                  View agenda
                </a>
              )}
            </div>
          </section>
        )}

        {/* ── Footer ── */}
        <footer className="py-8 border-t border-white/10 text-center">
          <Link href="/search" className="text-sm text-white/30 hover:text-white/60 transition-colors">
            Search
          </Link>
          <span className="mx-3 text-white/10">·</span>
          <Link href="/council" className="text-sm text-white/30 hover:text-white/60 transition-colors">
            Council
          </Link>
          <span className="mx-3 text-white/10">·</span>
          <Link href="/about" className="text-sm text-white/30 hover:text-white/60 transition-colors">
            About
          </Link>
          <p className="text-xs text-white/20 mt-3">
            richmondcommons.org
          </p>
        </footer>
      </div>
    </div>
  )
}
