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
// Deliberately NOT wrapped in try/catch: if the fetch fails on a cold
// cache, we want the loud "Try again" error rather than silently
// caching an empty-state page for 30 min, which would look like a
// working page but show no votes.
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
