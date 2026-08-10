import Link from 'next/link'
import SubscribeCTA from '@/components/SubscribeCTA'
import SourceBadge from '@/components/SourceBadge'
import FrontDoorCard from '@/components/FrontDoorCard'
import { buildElectionFrontDoorCard } from '@/components/front-door'
import { electionToSlug, getUpcomingElection } from '@/lib/queries'

export default async function Home() {
  const upcomingElection = await getUpcomingElection()
  const electionCard = buildElectionFrontDoorCard(
    upcomingElection,
    upcomingElection ? electionToSlug(upcomingElection) : null,
  )

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-12">
      <section className="mb-8 sm:mb-10">
        <h1 className="text-4xl font-bold text-civic-navy">Richmond Commons</h1>
        <p className="text-base text-slate-600 mt-1">
          Your city government, in one place and in plain language.
        </p>

        <form action="/search" method="get" role="search" className="mt-6">
          <label htmlFor="homepage-search" className="sr-only">
            Search a name, address, or topic
          </label>
          <div className="flex flex-col sm:flex-row gap-2">
            <input
              id="homepage-search"
              name="q"
              type="search"
              required
              placeholder="Search a name, address, or topic"
              className="min-h-11 flex-1 rounded-md border border-slate-300 bg-white px-4 py-3 text-base text-slate-900 shadow-sm placeholder:text-slate-500 focus:border-civic-navy focus:outline-none focus:ring-2 focus:ring-civic-navy/20"
            />
            <button
              type="submit"
              className="min-h-11 rounded-md bg-civic-navy px-6 py-3 text-base font-semibold text-white hover:bg-civic-navy-light focus:outline-none focus:ring-2 focus:ring-civic-navy focus:ring-offset-2"
            >
              Search
            </button>
          </div>
        </form>
      </section>

      <section aria-labelledby="front-door-heading">
        <h2 id="front-door-heading" className="sr-only">
          Meetings, elections, and council districts
        </h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <FrontDoorCard
            href="/meetings"
            eyebrow="Meetings"
            title="Council meetings"
            description="Browse council meeting agendas and votes."
          />

          <FrontDoorCard
            href={electionCard.href}
            eyebrow={electionCard.eyebrow}
            title={electionCard.title}
            description={electionCard.description}
          >
            {electionCard.source && (
              <SourceBadge
                tier={electionCard.source.tier}
                source={electionCard.source.name}
                extractedAt={electionCard.source.updatedAt}
              />
            )}
          </FrontDoorCard>

          <FrontDoorCard
            href="/elections/find-my-district"
            eyebrow="Council"
            title="Find My District"
            description="Look up your council district and representatives."
          />
        </div>
      </section>

      <SubscribeCTA surface="homepage" />

      <p className="text-center text-sm text-slate-500">
        <Link href="/about" className="inline-flex min-h-11 items-center font-medium text-civic-navy hover:text-civic-navy-light">
          About Richmond Commons
        </Link>
      </p>
    </div>
  )
}
