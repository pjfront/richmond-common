import type { Metadata } from 'next'
import OperatorGate from '@/components/OperatorGate'
import DataQualityDashboard from './DataQualityDashboard'

export const metadata: Metadata = {
  title: 'Data Quality',
  description: 'Data freshness, completeness, and anomaly monitoring for Richmond meeting data.',
}

export const revalidate = 3600

export default function DataQualityPage() {
  return (
    <OperatorGate
      fallback={
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <h1 className="text-3xl font-bold text-slate-900 mb-2">Data Quality</h1>
          <p className="text-slate-600">
            Data quality monitoring is not yet available. Check back soon.
          </p>
        </div>
      }
    >
      <DataQualityDashboard />
    </OperatorGate>
  )
}
