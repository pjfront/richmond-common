import type { Metadata } from 'next'
import Link from 'next/link'
import { getOfficials, getNeighborhoodCouncils } from '@/lib/queries'
import DistrictMap from '@/components/DistrictMap'
import type { Official } from '@/lib/types'

export const metadata: Metadata = {
  title: 'Council Districts — Richmond Commons',
  description:
    'Interactive map of Richmond\'s six city council districts. See who represents each district, explore boundaries, and find your neighborhood council.',
  openGraph: {
    title: 'Council Districts — Richmond Commons',
    description:
      'Explore Richmond\'s six council districts on an interactive map.',
  },
}

export default async function DistrictsPage() {
  const [officials, neighborhoodCouncils] = await Promise.all([
    getOfficials(undefined, { currentOnly: true, councilOnly: true }),
    getNeighborhoodCouncils(),
  ])

  // Filter to district-seated members (exclude mayor)
  const councilMembers = officials.filter(
    (o: Official) => o.seat && o.seat.startsWith('District'),
  )

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <Link
        href="/elections"
        className="text-sm text-civic-navy hover:underline mb-4 inline-block"
      >
        &larr; Elections
      </Link>

      <header className="mb-6">
        <h1 className="text-3xl font-bold text-civic-navy">
          Richmond Council Districts
        </h1>
        <p className="text-slate-600 mt-2 leading-relaxed max-w-2xl">
          Richmond is divided into six council districts, each represented by
          an elected council member. Hover over a district to see who
          represents it, or click to learn more.
        </p>
      </header>

      <DistrictMap
        officials={councilMembers}
        neighborhoodCouncils={neighborhoodCouncils}
      />

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
          {' '}(Adopted Map 201) via NDC Research. Council member data from official
          city records.
        </p>
      </footer>
    </div>
  )
}
