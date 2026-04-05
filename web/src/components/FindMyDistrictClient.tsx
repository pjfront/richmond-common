'use client'

import { useState, useCallback } from 'react'
import Link from 'next/link'
import {
  geocodeAddress,
  findDistrict,
  findNeighborhood,
  loadDistricts,
  loadNeighborhoods,
} from '@/lib/geo'
import type { DistrictMatch, NeighborhoodMatch } from '@/lib/geo'
import { officialToSlug } from '@/lib/queries'
import type { Official, CandidateFundraising } from '@/lib/types'

interface FindMyDistrictClientProps {
  councilMembers: Official[]
  mayor: Official | null
  candidates: CandidateFundraising[]
  electionDate: string | null
  electionName: string | null
}

type LookupState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; district: DistrictMatch; neighborhood: NeighborhoodMatch | null; matchedAddress: string }
  | { status: 'outside' }
  | { status: 'error'; message: string }

export default function FindMyDistrictClient({
  councilMembers,
  mayor,
  candidates,
  electionDate,
  electionName,
}: FindMyDistrictClientProps) {
  const [address, setAddress] = useState('')
  const [state, setState] = useState<LookupState>({ status: 'idle' })

  const handleLookup = useCallback(async () => {
    const trimmed = address.trim()
    if (!trimmed) return

    setState({ status: 'loading' })

    try {
      // 1. Geocode (browser → Census Bureau directly)
      const geo = await geocodeAddress(trimmed)

      // 2. Load GeoJSON (lazy, cached after first load)
      const [districts, neighborhoods] = await Promise.all([
        loadDistricts(),
        loadNeighborhoods(),
      ])

      // 3. Point-in-polygon (client-side, ~1ms)
      const district = findDistrict(geo.lat, geo.lng, districts)
      if (!district) {
        setState({ status: 'outside' })
        return
      }

      const neighborhood = findNeighborhood(geo.lat, geo.lng, neighborhoods)

      setState({
        status: 'success',
        district,
        neighborhood,
        matchedAddress: geo.matchedAddress,
      })
    } catch (err) {
      setState({
        status: 'error',
        message:
          err instanceof Error
            ? err.message
            : 'Something went wrong. Please try again.',
      })
    }
  }, [address])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleLookup()
  }

  // Derived data for the result
  const councilMember =
    state.status === 'success'
      ? councilMembers.find((o) =>
          o.seat?.includes(`District ${state.district.district}`),
        )
      : null

  const districtCandidates =
    state.status === 'success'
      ? candidates.filter((c) =>
          c.office_sought.includes(`District ${state.district.district}`),
        )
      : []

  const mayoralCandidates = candidates.filter(
    (c) => c.office_sought === 'Mayor',
  )

  const electionDateFormatted = electionDate
    ? new Date(electionDate + 'T00:00:00').toLocaleDateString('en-US', {
        month: 'long',
        day: 'numeric',
        year: 'numeric',
      })
    : null

  return (
    <div>
      {/* Address input */}
      <div className="flex gap-2 mb-2">
        <input
          type="text"
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="300 23rd St"
          className="flex-1 px-3 py-2 border border-slate-300 rounded-md text-sm
                     focus:outline-none focus:ring-2 focus:ring-civic-navy/30
                     focus:border-civic-navy placeholder:text-slate-400"
          aria-label="Street address in Richmond"
          disabled={state.status === 'loading'}
        />
        <button
          onClick={handleLookup}
          disabled={state.status === 'loading' || !address.trim()}
          className="px-4 py-2 bg-civic-navy text-white text-sm font-medium
                     rounded-md hover:bg-civic-navy-light transition-colors
                     disabled:opacity-50 disabled:cursor-not-allowed
                     whitespace-nowrap"
        >
          {state.status === 'loading' ? 'Looking up...' : 'Find my district'}
        </button>
      </div>

      {/* Status announcements for screen readers */}
      <div aria-live="polite" aria-atomic="true" className="sr-only">
        {state.status === 'loading' && 'Looking up your district...'}
        {state.status === 'success' &&
          `You live in District ${state.district.district}.`}
        {state.status === 'outside' &&
          'That address appears to be outside Richmond city limits.'}
        {state.status === 'error' && state.message}
      </div>

      {/* Loading */}
      {state.status === 'loading' && (
        <div className="mt-6 space-y-3 animate-pulse">
          <div className="h-6 bg-slate-200 rounded w-2/3" />
          <div className="h-4 bg-slate-200 rounded w-1/2" />
          <div className="h-20 bg-slate-200 rounded" />
        </div>
      )}

      {/* Result */}
      {state.status === 'success' && (
        <div className="mt-6 space-y-6">
          {/* District header */}
          <div className="bg-white border border-slate-200 rounded-lg p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-xl font-bold text-civic-navy">
                  You live in District {state.district.district}
                </h2>
                {state.neighborhood && (
                  <p className="text-sm text-slate-500 mt-1">
                    {titleCase(state.neighborhood.name)} neighborhood
                  </p>
                )}
              </div>
              <span className="inline-flex items-center justify-center w-10 h-10
                              bg-civic-navy text-white text-lg font-bold rounded-full
                              shrink-0">
                {state.district.district}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-3">
              Matched: {state.matchedAddress}
            </p>
          </div>

          {/* Current council member */}
          {councilMember && (
            <section>
              <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-2">
                Your Council Member
              </h3>
              <div className="bg-white border border-slate-200 rounded-lg p-4">
                <Link
                  href={`/council/${officialToSlug(councilMember.name)}`}
                  className="text-lg font-semibold text-civic-navy hover:underline"
                >
                  {councilMember.name}
                </Link>
                <p className="text-sm text-slate-600 mt-1">
                  {councilMember.role === 'vice_mayor'
                    ? 'Vice Mayor'
                    : 'Council Member'}
                  {', '}
                  {councilMember.seat}
                  {councilMember.term_end && (
                    <>
                      {' '}&middot; Term ends{' '}
                      {new Date(
                        councilMember.term_end + 'T00:00:00',
                      ).toLocaleDateString('en-US', {
                        month: 'long',
                        year: 'numeric',
                      })}
                    </>
                  )}
                </p>
              </div>
            </section>
          )}

          {/* Mayor */}
          {mayor && (
            <section>
              <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-2">
                Mayor
              </h3>
              <div className="bg-white border border-slate-200 rounded-lg p-4">
                <Link
                  href={`/council/${officialToSlug(mayor.name)}`}
                  className="text-lg font-semibold text-civic-navy hover:underline"
                >
                  {mayor.name}
                </Link>
                <p className="text-sm text-slate-600 mt-1">
                  Mayor of Richmond
                  {mayor.term_end && (
                    <>
                      {' '}&middot; Term ends{' '}
                      {new Date(
                        mayor.term_end + 'T00:00:00',
                      ).toLocaleDateString('en-US', {
                        month: 'long',
                        year: 'numeric',
                      })}
                    </>
                  )}
                </p>
              </div>
            </section>
          )}

          {/* Upcoming election */}
          {electionName && (
            <section>
              <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-2">
                {electionName}
                {electionDateFormatted && ` — ${electionDateFormatted}`}
              </h3>

              {/* District race */}
              {districtCandidates.length > 0 ? (
                <div className="bg-white border border-slate-200 rounded-lg p-4 mb-3">
                  <p className="text-sm text-slate-600 mb-3">
                    {districtCandidates.length === 1
                      ? `One candidate is running for your District ${state.district.district} seat:`
                      : `${districtCandidates.length} candidates are running for your District ${state.district.district} seat:`}
                  </p>
                  <ul className="space-y-2">
                    {districtCandidates.map((c) => (
                      <CandidateRow key={c.candidate_name} candidate={c} />
                    ))}
                  </ul>
                </div>
              ) : (
                <div className="bg-white border border-slate-200 rounded-lg p-4 mb-3">
                  <p className="text-sm text-slate-500 italic">
                    No contested race for District {state.district.district} in
                    this election.
                  </p>
                </div>
              )}

              {/* Mayoral race */}
              {mayoralCandidates.length > 0 && (
                <div className="bg-white border border-slate-200 rounded-lg p-4">
                  <p className="text-sm text-slate-600 mb-3">
                    {mayoralCandidates.length} candidates are running for
                    mayor (city-wide):
                  </p>
                  <ul className="space-y-2">
                    {mayoralCandidates.map((c) => (
                      <CandidateRow key={c.candidate_name} candidate={c} />
                    ))}
                  </ul>
                </div>
              )}
            </section>
          )}

          {/* CTA to election page */}
          {electionName && (
            <div className="text-center">
              <Link
                href="/elections/2026-primary"
                className="text-sm text-civic-navy hover:underline"
              >
                See full election details &rarr;
              </Link>
            </div>
          )}
        </div>
      )}

      {/* Outside Richmond */}
      {state.status === 'outside' && (
        <div className="mt-6 bg-amber-50 border border-amber-200 rounded-lg p-4">
          <p className="text-sm text-amber-800">
            That address appears to be outside Richmond city limits. This
            tool covers the six city council districts within Richmond,
            California.
          </p>
        </div>
      )}

      {/* Error */}
      {state.status === 'error' && (
        <div className="mt-6 bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-sm text-red-800">{state.message}</p>
        </div>
      )}
    </div>
  )
}

// ─── Candidate row ──────────────────────────────────────────────────────────

function CandidateRow({ candidate }: { candidate: CandidateFundraising }) {
  const raised = candidate.total_raised
  return (
    <li className="flex items-center justify-between text-sm">
      <span>
        <span className="font-medium text-civic-navy">
          {candidate.candidate_name}
        </span>
        {candidate.is_incumbent && (
          <span className="ml-1.5 text-xs bg-civic-navy/10 text-civic-navy px-1.5 py-0.5 rounded">
            incumbent
          </span>
        )}
      </span>
      {raised > 0 ? (
        <span className="text-slate-500 tabular-nums">
          ${raised.toLocaleString('en-US', { maximumFractionDigits: 0 })} raised
        </span>
      ) : (
        <span className="text-slate-400 italic text-xs">
          no filings yet
        </span>
      )}
    </li>
  )
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function titleCase(str: string): string {
  return str
    .toLowerCase()
    .split(/[\s/]+/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}
