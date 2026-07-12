import type { Metadata } from 'next'
import RecapStatePanel from './RecapStatePanel'

export const metadata: Metadata = {
  title: 'Recap State — Operator',
  description: 'Monitor recap coverage across recent council meetings.',
}

export default function RecapsPage() {
  return (
    <div className="max-w-4xl mx-auto py-8 px-4">
      <h1 className="text-2xl font-semibold text-civic-navy mb-1">Recap State</h1>
      <p className="text-sm text-slate-500 mb-6">
        Meetings missing transcript or meeting recaps. Highlighted rows need attention.
      </p>
      <RecapStatePanel />
    </div>
  )
}
