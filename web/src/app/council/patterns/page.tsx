import type { Metadata } from 'next'
import PatternsDashboard from './PatternsDashboard'

// Dynamic rendering — cross-meeting pattern analysis fetches large contribution
// and vote datasets, too heavy for static generation build workers.
export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Cross-Meeting Patterns — Contribution & Legislative Analysis',
  description: 'Donor-category concentration patterns and cross-official contribution overlap analysis for Richmond city government.',
}

export default function PatternsPage() {
  return <PatternsDashboard />
}
