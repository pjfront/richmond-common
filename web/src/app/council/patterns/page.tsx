import type { Metadata } from 'next'
import OperatorGate from '@/components/OperatorGate'
import PatternsDashboard from './PatternsDashboard'

export const revalidate = 3600

export const metadata: Metadata = {
  title: 'Cross-Meeting Patterns — Contribution & Legislative Analysis',
  description: 'Donor-category concentration patterns and cross-official contribution overlap analysis for Richmond city government.',
}

export default function PatternsPage() {
  return (
    <OperatorGate
      fallback={
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <h1 className="text-3xl font-bold text-slate-900 mb-2">Cross-Meeting Patterns</h1>
          <p className="text-slate-600">
            Pattern analysis is not yet available. Check back soon.
          </p>
        </div>
      }
    >
      <PatternsDashboard />
    </OperatorGate>
  )
}
