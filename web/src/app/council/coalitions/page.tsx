import type { Metadata } from 'next'
import OperatorGate from '@/components/OperatorGate'
import CoalitionDashboard from './CoalitionDashboard'

export const revalidate = 3600

export const metadata: Metadata = {
  title: 'Voting Coalitions — Council Alignment Analysis',
  description: 'Pairwise voting alignment, bloc detection, and category divergence analysis for the Richmond City Council.',
}

export default function CoalitionsPage() {
  return (
    <OperatorGate
      fallback={
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <h1 className="text-3xl font-bold text-slate-900 mb-2">Voting Coalitions</h1>
          <p className="text-slate-600">
            Coalition analysis is not yet available. Check back soon.
          </p>
        </div>
      }
    >
      <CoalitionDashboard />
    </OperatorGate>
  )
}
