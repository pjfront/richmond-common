import type { Metadata } from 'next'
import Link from 'next/link'
import {
  getOfficials,
  getUpcomingElection,
  getElectionFundraisingSummary,
  getNeighborhoodCouncils,
} from '@/lib/queries'
import FindMyDistrictClient from '@/components/FindMyDistrictClient'
import type { Official, CandidateFundraising } from '@/lib/types'

export const metadata: Metadata = {
  title: 'Find My District — Richmond Commons',
  description:
    'Enter your Richmond address to find your city council district, current representative, neighborhood council, and upcoming election candidates.',
  openGraph: {
    title: 'Find My District — Richmond Commons',
    description:
      'Look up your Richmond council district and see who represents you.',
  },
}

export default async function FindMyDistrictPage() {
  return <FindMyDistrictContent />
}

async function FindMyDistrictContent() {
  // Pre-fetch at ISR time: current officials + upcoming election + neighborhood councils
  const [officials, upcomingElection, neighborhoodCouncils] = await Promise.all([
    getOfficials(undefined, { currentOnly: true, councilOnly: true }),
    getUpcomingElection(),
    getNeighborhoodCouncils(),
  ])

  // Include the mayor (councilOnly filters to COUNCIL_ROLES which includes mayor)
  const councilMembers = officials.filter(
    (o: Official) => o.seat && o.seat.startsWith('District'),
  )
  const mayor = officials.find((o: Official) => o.seat === 'Mayor') ?? null

  let candidates: CandidateFundraising[] = []
  let electionDate: string | null = null
  let electionName: string | null = null

  if (upcomingElection) {
    candidates = await getElectionFundraisingSummary(upcomingElection.id, undefined, upcomingElection.election_date)
    electionDate = upcomingElection.election_date
    electionName = upcomingElection.election_name
  }

  return (
    <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <Link
        href="/elections"
        className="text-sm text-civic-navy hover:underline mb-4 inline-block"
      >
        &larr; Elections
      </Link>

      <header className="mb-8">
        <h1 className="text-3xl font-bold text-civic-navy">
          Find My District
        </h1>
        <p className="text-slate-600 mt-2 leading-relaxed">
          Enter your Richmond address to find your city council district,
          who represents you, your neighborhood council, and who&apos;s
          running in the next election.
        </p>
      </header>

      <FindMyDistrictClient
        councilMembers={councilMembers}
        mayor={mayor}
        candidates={candidates}
        electionDate={electionDate}
        electionName={electionName}
        neighborhoodCouncils={neighborhoodCouncils}
      />

      {/* Source attribution */}
      <footer className="mt-10 pt-6 border-t border-slate-200 space-y-2">
        <p className="text-xs text-slate-500">
          District boundaries from the{' '}
          <a
            href="https://experience.arcgis.com/experience/59a7bd37246744f498b546ecf9e4f28b"
            target="_blank"
            rel="noopener noreferrer"
            className="text-civic-navy hover:underline"
          >
            2021 Redistricting Map
          </a>
          {' '}via NDC Research. Address lookup powered by the Census Bureau Geocoder.
          Neighborhood council data from the{' '}
          <a
            href="https://www.ci.richmond.ca.us/267/Neighborhood-Councils"
            target="_blank"
            rel="noopener noreferrer"
            className="text-civic-navy hover:underline"
          >
            City of Richmond
          </a>
          .
        </p>
        <p className="text-xs text-slate-400">
          Your address is forwarded to the U.S. Census Bureau for
          geocoding and is not stored or logged by Richmond Commons.
        </p>
      </footer>
    </div>
  )
}
