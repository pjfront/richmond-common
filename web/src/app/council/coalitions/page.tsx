import type { Metadata } from 'next'
import CoalitionDashboard from './CoalitionDashboard'

// Dynamic rendering — coalition analysis fetches 55K+ votes with nested joins,
// too large for static generation build workers running in parallel.
export const dynamic = 'force-dynamic'
// Allow up to 60s for the heavy pairwise alignment computation (default 10s times out)
export const maxDuration = 60

export const metadata: Metadata = {
  title: 'Voting Coalitions — Council Alignment Analysis',
  description: 'Pairwise voting alignment, bloc detection, and category divergence analysis for the Richmond City Council.',
}

export default function CoalitionsPage() {
  return <CoalitionDashboard />
}
