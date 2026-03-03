import type { Metadata } from 'next'
import DataQualityDashboard from './DataQualityDashboard'

export const metadata: Metadata = {
  title: 'Data Quality',
  description: 'Data freshness, completeness, and anomaly monitoring for Richmond meeting data.',
}

export const revalidate = 3600

export default function DataQualityPage() {
  return <DataQualityDashboard />
}
