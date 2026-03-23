import type { Metadata } from 'next'
import PatternsDashboard from './PatternsDashboard'
import OperatorGate from '@/components/OperatorGate'

// ISR: cache for 30 minutes — heavy pairwise computation but deterministic
export const revalidate = 1800
export const maxDuration = 60

export const metadata: Metadata = {
  title: 'Cross-Meeting Patterns — Contribution & Legislative Analysis',
  description: 'Donor-category concentration patterns and cross-official contribution overlap analysis for Richmond city government.',
}

export default function PatternsPage() {
  return (
    <OperatorGate>
      <PatternsDashboard />
    </OperatorGate>
  )
}
