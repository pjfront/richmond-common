import type { Metadata } from 'next'
import PatternsDashboard from './PatternsDashboard'

export const revalidate = 3600

export const metadata: Metadata = {
  title: 'Cross-Meeting Patterns — Contribution & Legislative Analysis',
  description: 'Donor-category concentration patterns and cross-official contribution overlap analysis for Richmond city government.',
}

export default function PatternsPage() {
  return <PatternsDashboard />
}
