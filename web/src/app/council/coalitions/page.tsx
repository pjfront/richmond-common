import type { Metadata } from 'next'
import CoalitionDashboard from './CoalitionDashboard'

export const revalidate = 3600

export const metadata: Metadata = {
  title: 'Voting Coalitions — Council Alignment Analysis',
  description: 'Pairwise voting alignment, bloc detection, and category divergence analysis for the Richmond City Council.',
}

export default function CoalitionsPage() {
  return <CoalitionDashboard />
}
