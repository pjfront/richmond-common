import Link from 'next/link'
import type { Metadata } from 'next'
import { getMeetingsWithFlags } from '@/lib/queries'
import LastUpdated from '@/components/LastUpdated'
import OperatorGate from '@/components/OperatorGate'


export const metadata: Metadata = {
  title: 'Financial Contribution Reports',
  description: 'Analysis of Richmond City Council meetings — conflict of interest scanning and campaign finance cross-referencing.',
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', {
    weekday: 'short',
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export default async function ReportsListPage() {
  return (
    <OperatorGate>
      <ReportsListContent />
    </OperatorGate>
  )
}

async function ReportsListContent() {
  const meetings = await getMeetingsWithFlags()

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-3xl font-bold text-civic-navy mb-2">Financial Contribution Reports</h1>
      <p className="text-slate-600 mb-8">
        Each report cross-references agenda items against campaign contributions and financial
        disclosures to identify potential conflicts of interest.
      </p>

      {meetings.length === 0 ? (
        <p className="text-slate-500 italic">No scanned meetings available yet.</p>
      ) : (
        <div className="space-y-3">
          {meetings.map((m) => (
            <Link
              key={m.id}
              href={`/reports/${m.id}`}
              className="block bg-white rounded-lg border border-slate-200 p-4 hover:border-civic-navy-light hover:shadow-sm transition-all"
            >
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-semibold text-slate-900">{formatDate(m.meeting_date)}</h3>
                  <p className="text-sm text-slate-500 mt-1">
                    {m.items_scanned} items scanned
                  </p>
                </div>
                <div className="text-right">
                  {m.flags_published > 0 ? (
                    <span className="inline-block text-sm font-semibold px-3 py-1 rounded-full bg-civic-amber/10 text-civic-amber">
                      {m.flags_published} flag{m.flags_published !== 1 ? 's' : ''}
                    </span>
                  ) : (
                    <span className="inline-block text-sm font-medium px-3 py-1 rounded-full bg-green-50 text-green-700">
                      Clean
                    </span>
                  )}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
      <LastUpdated />
    </div>
  )
}
