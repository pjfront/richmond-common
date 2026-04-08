import type { Metadata } from 'next'
import CoalitionDashboard from './CoalitionDashboard'
import OperatorGate from '@/components/OperatorGate'

// Skip build-time generation — this operator-only page has a heavy pairwise
// alignment query that times out during Vercel builds. ISR still caches at runtime.
export const dynamic = 'force-dynamic'
export const maxDuration = 60

export const metadata: Metadata = {
  title: 'Voting Coalitions | Council Alignment Analysis',
  description: 'Pairwise voting alignment, bloc detection, and category divergence analysis for the Richmond City Council.',
}

export default function CoalitionsPage() {
  return (
    <OperatorGate>
      <CoalitionDashboard />
    </OperatorGate>
  )
}
