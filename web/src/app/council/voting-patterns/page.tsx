import type { Metadata } from 'next'
import { getCoalitionData, getDivergentMotions } from '@/lib/queries'
import VotingPatternsDashboard from './VotingPatternsDashboard'

// Render on demand, not at build. The page calls heavy RPCs
// (get_coalition_data, get_divergent_motions_detail) that exceed the
// anon-role statement_timeout when 27 build workers hit Supabase
// concurrently — which has been the dominant cause of failed production
// deploys since 2026-05-06. On a real user request the page is rendered
// alone and the RPCs complete within budget.
//
// Throw-on-error semantics for normal operation are preserved: if either
// RPC fails at request time, the page throws and Next.js renders error.tsx
// ("Couldn't load voting records / Try again") instead of a misleading
// "Showing 0 of 0 split votes" empty state. The previous ISR cache-on-
// stale behavior is lost (force-dynamic disables ISR), accepted as a
// trade-off until the underlying RPCs are optimized in Phase 2.
export const dynamic = 'force-dynamic'
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
