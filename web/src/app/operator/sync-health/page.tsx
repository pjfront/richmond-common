import type { Metadata } from 'next'
import SyncHealthDashboard from './SyncHealthDashboard'

export const metadata: Metadata = {
  title: 'Sync Health Dashboard',
  description: 'Pipeline sync status, schedule, and failure tracking.',
}

export default function SyncHealthPage() {
  return <SyncHealthDashboard />
}
