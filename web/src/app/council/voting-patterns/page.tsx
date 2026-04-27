import type { Metadata } from 'next'
import { getCoalitionData, getDivergentMotions } from '@/lib/queries'
import VotingPatternsDashboard from './VotingPatternsDashboard'

// Heavy aggregation queries that exceed the Vercel build timeout. ISR still
// caches at runtime — the page is public after Phase A graduation.
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
      blocs={coalition.blocs}
      divergences={coalition.divergences}
      coalitionOfficials={coalition.officials}
      motions={divergent.motions}
      motionOfficials={divergent.officials}
    />
  )
}
