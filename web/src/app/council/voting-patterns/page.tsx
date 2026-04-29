import type { Metadata } from 'next'
import { getCoalitionData, getDivergentMotions } from '@/lib/queries'
import VotingPatternsDashboard from './VotingPatternsDashboard'

// ISR: render once, cache for 30 min, revalidate in background.
//
// The previous `force-dynamic` setting made every request re-run both
// heavy aggregations with no cache. Any transient Supabase blip or
// Vercel cold-start would surface as the user-facing error.tsx — which
// is what motivated the operator's "I see this transient page a few
// times" report 2026-04-29.
//
// With ISR:
//  - Successful renders cache for 30 min; subsequent requests are fast
//    cache hits with no DB load.
//  - During revalidation, Vercel keeps serving the previous cached
//    page; if the revalidation fetch fails, the prior good cache stays
//    valid for the next attempt. Users never see the error during the
//    common transient case (cache exists + one bad fetch).
//  - error.tsx still triggers in the rare cold-cache + failed-fetch
//    case (first request after deploy, no prior cache to fall back to).
//    The "Try again" button there reloads and usually succeeds.
//
// The two RPCs (get_contested_votes + get_divergent_motions_detail)
// take ~3s combined against the live DB — well under any reasonable
// timeout. The original concern about exceeding Vercel build timeout
// no longer applies. maxDuration kept at 60s as a defense in depth.
//
// Build-time tolerance: wrap fetches in try/catch so the build prerender
// succeeds even when concurrent fetches hit Supabase statement timeouts.
// Build runs all ISR prerenders in parallel; pool contention can cause
// individual queries to time out during build that succeed at runtime.
// Without this, the entire deploy fails. With this, a failed prerender
// renders the empty state (briefly cached) and ISR's first revalidation
// cycle fills in real data on the next request after deploy.
export const revalidate = 1800
export const maxDuration = 60

export const metadata: Metadata = {
  title: 'How the Council Votes | Richmond Commons',
  description:
    'See where Richmond City Council members vote together, where they split, and on which issues. Based on contested votes from public meeting minutes.',
}

export default async function VotingPatternsPage() {
  let coalition: Awaited<ReturnType<typeof getCoalitionData>> = {
    alignments: [],
    divergences: [],
    officials: [],
  }
  let divergent: Awaited<ReturnType<typeof getDivergentMotions>> = {
    motions: [],
    officials: [],
  }
  try {
    const [c, d] = await Promise.all([
      getCoalitionData(),
      getDivergentMotions(),
    ])
    coalition = c
    divergent = d
  } catch (err) {
    console.error('[voting-patterns] data fetch failed, rendering empty state:', err)
  }

  return (
    <VotingPatternsDashboard
      alignments={coalition.alignments}
      coalitionOfficials={coalition.officials}
      motions={divergent.motions}
      motionOfficials={divergent.officials}
    />
  )
}
