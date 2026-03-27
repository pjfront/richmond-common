import Link from 'next/link'
import type { Metadata } from 'next'
import { getElections } from '@/lib/queries'
import OperatorGate from '@/components/OperatorGate'

export const dynamic = 'force-dynamic'
export const revalidate = 3600

export const metadata: Metadata = {
  title: 'Election Cycles — Richmond Common',
  description:
    'Track election cycles in Richmond, California. See candidates, fundraising, and campaign finance connections.',
}

export default async function ElectionsIndexPage() {
  return (
    <OperatorGate>
      <ElectionsIndexContent />
    </OperatorGate>
  )
}

async function ElectionsIndexContent() {
  const elections = await getElections()

  const upcoming = elections.filter(
    (e) => new Date(e.election_date) >= new Date(),
  )
  const past = elections.filter(
    (e) => new Date(e.election_date) < new Date(),
  )

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-civic-navy">Election Cycles</h1>
        <p className="text-sm text-slate-600 mt-2 max-w-2xl leading-relaxed">
          Richmond election cycles with linked candidates and campaign finance data.
          Contributions are matched to elections by committee filing records and
          contribution dates.
        </p>
      </header>

      {elections.length === 0 && (
        <p className="text-slate-500 italic">
          No election data available yet. Election records are populated from
          campaign finance filings.
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

      <footer className="mt-10 pt-6 border-t border-slate-200">
        <p className="text-xs text-slate-400">
          Election dates from the California Secretary of State. Candidate and
          fundraising data derived from NetFile and CAL-ACCESS campaign finance
          filings. This data is automatically updated and may contain matching
          errors.
        </p>
      </footer>
    </div>
  )
}

function ElectionCard({ election }: { election: Awaited<ReturnType<typeof getElections>>[0] }) {
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
      href={`/influence/elections/${election.id}`}
      className="block bg-white border border-slate-200 rounded-lg p-5 hover:border-civic-navy/30 hover:shadow-sm transition-all"
    >
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-lg font-semibold text-civic-navy">
            {election.election_name || `${election.election_type} Election`}
          </h3>
          <p className="text-sm text-slate-600 mt-1">{formattedDate}</p>
          {election.jurisdiction && (
            <p className="text-xs text-slate-400 mt-1">{election.jurisdiction}</p>
          )}
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
      {election.notes && (
        <p className="text-xs text-slate-500 mt-3 leading-relaxed">
          {election.notes}
        </p>
      )}
    </Link>
  )
}
