import type { Metadata } from 'next'
import CoalitionDashboard from './CoalitionDashboard'
import OperatorGate from '@/components/OperatorGate'

// Allow up to 60s for the heavy pairwise alignment computation (default 10s times out).
// ISR caches the result hourly (inherited from layout), so this only runs on revalidation.
export const maxDuration = 60

export const metadata: Metadata = {
  title: 'Voting Coalitions — Council Alignment Analysis',
  description: 'Pairwise voting alignment, bloc detection, and category divergence analysis for the Richmond City Council.',
}

export default function CoalitionsPage() {
  return (
    <OperatorGate>
      <CoalitionDashboard />
    </OperatorGate>
  )
}
