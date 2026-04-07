import Link from 'next/link'
import type { Metadata } from 'next'
import { getElections } from '@/lib/queries'
import type { Election } from '@/lib/types'
import SubscribeCTA from '@/components/SubscribeCTA'


export const metadata: Metadata = {
  title: 'Elections — Richmond Commons',
  description:
    'Richmond, California elections: candidates, campaign fundraising, and voter information. Track who is running and how campaigns are funded.',
}

/** Generate a URL slug from an election record. */
function electionSlug(election: Election): string {
  const year = election.election_date.split('-')[0]
  return `${year}-${election.election_type}`
}

export default async function ElectionsIndexPage() {
  return <ElectionsIndexContent />
}

async function ElectionsIndexContent() {
  const elections = await getElections()

  const upcoming = elections
    .filter((e) => new Date(e.election_date) >= new Date())
    .sort((a, b) => new Date(a.election_date).getTime() - new Date(b.election_date).getTime())
  const past = elections.filter(
    (e) => new Date(e.election_date) < new Date(),
  )

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-civic-navy">Elections</h1>
        <p className="text-sm text-slate-600 mt-2 max-w-2xl leading-relaxed">
          Richmond election cycles with linked candidates and campaign finance
          data from public filings.
        </p>
      </header>

      {elections.length === 0 && (
        <p className="text-slate-500 italic">
          No election data available yet.
        </p>
      )}

      {upcoming.length > 0 && (
        <section className="mb-10">
          <h2 className="text-xl font-semibold text-civic-navy mb-4">
            Upcoming Elections
          </h2>
          <div className="space-y-4">
            {upcoming.map((election) => (
              <ElectionCard key={election.id} election={election} />
            ))}
          </div>
        </section>
      )}

      {past.length > 0 && (
        <section>
          <h2 className="text-xl font-semibold text-civic-navy mb-4">
            Past Elections
          </h2>
          <div className="space-y-4">
            {past.map((election) => (
              <ElectionCard key={election.id} election={election} />
            ))}
          </div>
        </section>
      )}

      {/* Stay informed CTA */}
      <SubscribeCTA />

      <footer className="mt-10 pt-6 border-t border-slate-200">
        <p className="text-xs text-slate-400">
          Election dates from the California Secretary of State. Candidate and
          fundraising data from NetFile and CAL-ACCESS campaign finance filings.
        </p>
      </footer>
    </div>
  )
}

function ElectionCard({ election }: { election: Election }) {
  const date = new Date(election.election_date + 'T00:00:00')
  const formattedDate = date.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })

  const isUpcoming = date >= new Date()
  const daysUntil = Math.ceil(
    (date.getTime() - Date.now()) / (1000 * 60 * 60 * 24),
  )

  return (
    <Link
      href={`/elections/${electionSlug(election)}`}
      className="block bg-white border border-slate-200 rounded-lg p-5 hover:border-civic-navy/30 hover:shadow-sm transition-all"
    >
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-lg font-semibold text-civic-navy">
            {election.election_name || `${election.election_type} Election`}
          </h3>
          <p className="text-sm text-slate-600 mt-1">{formattedDate}</p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span
            className={`inline-block px-2 py-0.5 text-xs font-medium rounded ${
              election.election_type === 'primary'
                ? 'bg-blue-50 text-blue-700'
                : election.election_type === 'general'
                  ? 'bg-green-50 text-green-700'
                  : 'bg-slate-50 text-slate-600'
            }`}
          >
            {election.election_type}
          </span>
          {isUpcoming && daysUntil > 0 && (
            <span className="text-xs text-civic-amber font-medium">
              {daysUntil} days away
            </span>
          )}
        </div>
      </div>
    </Link>
  )
}
