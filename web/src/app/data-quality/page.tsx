import type { Metadata } from 'next'
import DataQualityDashboard from './DataQualityDashboard'
import OperatorGate from '@/components/OperatorGate'
import { requireOperatorPage } from '@/lib/operator-page'

export const metadata: Metadata = {
  title: 'Data Quality',
  description: 'Data freshness, completeness, and anomaly monitoring for Richmond meeting data.',
  robots: { index: false, follow: false },
}


export default async function DataQualityPage() {
  await requireOperatorPage()

  return (
    <OperatorGate>
      <DataQualityDashboard />
    </OperatorGate>
  )
}
