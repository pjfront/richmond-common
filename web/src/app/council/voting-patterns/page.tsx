import type { Metadata } from 'next'
import { getCoalitionData, getDivergentMotions } from '@/lib/queries'
import VotingPatternsDashboard from './VotingPatternsDashboard'

// ISR with throw-on-error: render once, cache for 30 min, revalidate in background.
//
// We intentionally do NOT swallow fetch errors. If either RPC fails, the page
// throws and Next.js renders error.tsx ("Couldn't load voting records / Try
// again") instead of a misleading "Showing 0 of 0 split votes" empty state.
// On ISR revalidation, a thrown render does NOT overwrite the existing cache,
// so users keep seeing the last good page until the next successful fetch.
//
// The earlier try/catch pattern (catching errors and rendering an empty
// dashboard) made transient Supabase statement_timeout hits indistinguishable
// from "no contested votes exist," and once the empty state was cached it
// could persist for a full revalidate cycle.
export const revalidate = 1800
export const maxDuration = 60

export const metadata: Metadata = {
  title: 'How the Council Votes | Richmond Commons',
  description:
    'See where Richmond City Council members vote together, where they split, and on which issues. Based on contested votes from public meeting minutes.',
}

export default async function VotingPatternsPage() {
  const [coalition, divergent] = await Promise.all([
    getCoalitionData(),
    getDivergentMotions(),
  ])

  return (
    <VotingPatternsDashboard
      alignments={coalition.alignments}
      coalitionOfficials={coalition.officials}
      motions={divergent.motions}
      motionOfficials={divergent.officials}
    />
  )
}
