import type { Metadata } from 'next'
import DataQualityDashboard from './DataQualityDashboard'
import OperatorGate from '@/components/OperatorGate'

export const metadata: Metadata = {
  title: 'Data Quality',
  description: 'Data freshness, completeness, and anomaly monitoring for Richmond meeting data.',
}


export default function DataQualityPage() {
  return (
    <OperatorGate>
      <DataQualityDashboard />
    </OperatorGate>
  )
}
