import Link from 'next/link'
import { notFound } from 'next/navigation'
import { getOfficialBySlug, getOfficialVotingRecord, getOfficialContributions } from '@/lib/queries'

export const metadata = { title: 'Council Member — The Record' }

const serif = { fontFamily: 'Georgia, "Times New Roman", serif' }
const sans = { fontFamily: 'Inter, system-ui, sans-serif' }

function formatRole(role: string): string {
  if (role === 'mayor') return 'Mayor'
  if (role === 'vice_mayor') return 'Vice Mayor'
  return 'Council Member'
}

function tinyDate(dateStr: string): string {
  return new Date(dateStr + 'T12:00:00').toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
  })
}

function monthYear(dateStr: string): string {
  return new Date(dateStr + 'T12:00:00').toLocaleDateString('en-US', {
    month: 'long', year: 'numeric',
  })
}

function formatMoney(amount: number): string {
  if (amount >= 1000) return `$${(amount / 1000).toFixed(amount % 1000 === 0 ? 0 : 1)}k`
  return `$${Math.round(amount)}`
}

export default async function RecordCouncilPage({
  params,
}: {
  params: Promise<{ slug: string }>
}) {
  const { slug } = await params
  const official = await getOfficialBySlug(slug)
  if (!official) notFound()

  const [votingRecord, contributions] = await Promise.all([
    getOfficialVotingRecord(official.id),
    getOfficialContributions(official.id),
  ])

  // Parse voting record into something useful
  type VoteRecord = {
    date: string
    title: string
    voteChoice: string
    result: string
    tally: string | null
    meetingId: string
    isConsentCalendar: boolean
    category: string | null
    commentCount: number
  }

  const votes: VoteRecord[] = votingRecord.map((v) => {
    const motion = v.motions as unknown as {
      result: string; vote_tally: string | null;
      agenda_items: {
        id: string; title: string; category: string | null;
        is_consent_calendar: boolean; public_comment_count: number | null;
        meetings: { id: string; meeting_date: string }
      }
    }
    const item = motion.agenda_items
    const meeting = item.meetings
    return {
      date: meeting.meeting_date,
      title: item.title,
      voteChoice: v.vote_choice as string,
      result: motion.result,
      tally: motion.vote_tally,
      meetingId: meeting.id,
      isConsentCalendar: item.is_consent_calendar,
      category: item.category,
      commentCount: item.public_comment_count ?? 0,
    }
  }).sort((a, b) => b.date.localeCompare(a.date))

  // Filter to non-consent, non-unanimous (the interesting ones)
  const substantiveVotes = votes.filter(v => !v.isConsentCalendar)
  const dissentVotes = substantiveVotes.filter(v => {
    const choice = v.voteChoice.toLowerCase()
    return (choice === 'nay' || choice === 'no') && v.result.toLowerCase().includes('pass')
  })
  const recentVotes = substantiveVotes.slice(0, 8)

  // Aggregate contributions
  const totalRaised = contributions.reduce((sum, c) => sum + Number(c.amount), 0)
  const donorCount = new Set(contributions.map(c => c.donor_name)).size

  // Top donors
  const donorTotals = new Map<string, number>()
  for (const c of contributions) {
    donorTotals.set(c.donor_name, (donorTotals.get(c.donor_name) ?? 0) + Number(c.amount))
  }
  const topDonors = Array.from(donorTotals.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)

  // Top categories from voting record
  const categoryCounts = new Map<string, number>()
  for (const v of substantiveVotes) {
    if (v.category) categoryCounts.set(v.category, (categoryCounts.get(v.category) ?? 0) + 1)
  }
  const topCategories = Array.from(categoryCounts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)

  return (
    <div className="max-w-[640px] mx-auto px-5 pb-20" style={serif}>

      {/* ── Header ── */}
      <header className="pt-12 pb-8 border-b border-neutral-200">
        <p className="text-sm text-neutral-400 mb-2" style={sans}>
          {formatRole(official.role)}{official.is_current ? '' : ' (former)'}
        </p>
        <h1 className="text-3xl font-bold text-neutral-900">
          {official.name}
        </h1>
        {official.term_end && official.is_current && (
          <p className="text-neutral-500 mt-2">
            Term ends {monthYear(official.term_end)}
          </p>
        )}
      </header>

      {/* ── Bio / Summary ── */}
      {official.bio_summary && (
        <article className="pt-8 pb-8 border-b border-neutral-100">
          <div className="space-y-3 text-[17px] text-neutral-700 leading-relaxed">
            {official.bio_summary.split('\n\n').filter(Boolean).slice(0, 3).map((para, i) => (
              <p key={i}>{para}</p>
            ))}
          </div>
          <p className="mt-4 text-sm text-neutral-400" style={sans}>
            Auto-generated from voting record and public filings
          </p>
        </article>
      )}

      {/* ── What they spend their time on ── */}
      {topCategories.length > 0 && (
        <section className="pt-8 pb-8 border-b border-neutral-100">
          <h2 className="text-xs font-medium text-neutral-400 uppercase tracking-widest mb-4" style={sans}>
            Most voted-on topics
          </h2>
          <div className="space-y-1">
            {topCategories.map(([cat, count]) => (
              <p key={cat} className="text-[17px] text-neutral-700">
                {cat} <span className="text-neutral-400 text-sm" style={sans}>{count} votes</span>
              </p>
            ))}
          </div>
        </section>
      )}

      {/* ── Times they voted no when the motion passed ── */}
      {dissentVotes.length > 0 && (
        <section className="pt-8 pb-8 border-b border-neutral-100">
          <h2 className="text-xs font-medium text-neutral-400 uppercase tracking-widest mb-5" style={sans}>
            Voted against the majority
          </h2>
          <div className="space-y-4">
            {dissentVotes.slice(0, 5).map((v, i) => (
              <div key={i}>
                <Link
                  href={`/prototype/record/meeting/${v.meetingId}`}
                  className="text-[17px] text-neutral-800 hover:text-neutral-500 transition-colors leading-snug"
                >
                  {v.title}
                </Link>
                <p className="text-sm text-neutral-400 mt-0.5" style={sans}>
                  Voted no · {v.result} · {tinyDate(v.date)}
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Recent votes (compact feed) ── */}
      {recentVotes.length > 0 && (
        <section className="pt-8 pb-8 border-b border-neutral-100">
          <h2 className="text-xs font-medium text-neutral-400 uppercase tracking-widest mb-5" style={sans}>
            Recent votes
          </h2>
          <div className="space-y-3">
            {recentVotes.map((v, i) => (
              <div key={i} className="flex gap-4 items-baseline">
                <time className="text-sm text-neutral-400 shrink-0 w-16 text-right tabular-nums" style={sans}>
                  {tinyDate(v.date).replace(/, \d{4}$/, '')}
                </time>
                <div className="min-w-0">
                  <Link
                    href={`/prototype/record/meeting/${v.meetingId}`}
                    className="text-neutral-700 hover:text-neutral-500 transition-colors text-sm"
                    style={sans}
                  >
                    {v.title.length > 80 ? v.title.slice(0, 77) + '...' : v.title}
                  </Link>
                  <span className="text-neutral-400 text-sm ml-1.5" style={sans}>
                    {v.voteChoice.toLowerCase()}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Campaign money ── */}
      {totalRaised > 0 && (
        <section className="pt-8 pb-8 border-b border-neutral-100">
          <h2 className="text-xs font-medium text-neutral-400 uppercase tracking-widest mb-4" style={sans}>
            Campaign contributions
          </h2>
          <p className="text-[17px] text-neutral-700 mb-4">
            {formatMoney(totalRaised)} raised from {donorCount} {donorCount === 1 ? 'donor' : 'donors'}.
          </p>
          {topDonors.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-sm text-neutral-400 mb-2" style={sans}>Largest contributors</p>
              {topDonors.map(([name, amount]) => (
                <p key={name} className="text-sm" style={sans}>
                  <span className="text-neutral-700">{name}</span>
                  <span className="text-neutral-400 ml-1.5">{formatMoney(amount)}</span>
                </p>
              ))}
            </div>
          )}
          <p className="mt-4 text-sm text-neutral-400" style={sans}>
            From NetFile electronic filings (2018–present)
          </p>
        </section>
      )}

      {/* ── Source / full profile link ── */}
      <section className="pt-8 pb-8 border-b border-neutral-100">
        <div className="flex gap-6 text-sm text-neutral-400" style={sans}>
          <Link href={`/council/${slug}`}
            className="underline decoration-neutral-300 hover:text-neutral-600">
            Full profile with all votes &amp; donors
          </Link>
        </div>
      </section>

      {/* ── Navigation ── */}
      <nav className="pt-8 pb-8 flex justify-between text-sm" style={sans}>
        <Link href="/prototype/record" className="text-neutral-400 hover:text-neutral-600">
          &larr; Home
        </Link>
      </nav>
    </div>
  )
}
