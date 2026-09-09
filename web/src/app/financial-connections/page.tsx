import Link from 'next/link'
import type { Metadata } from 'next'
import FinancialConnectionsAllTable from '@/components/FinancialConnectionsAllTable'
import { requireOperatorPage } from '@/lib/operator-page'

export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Financial Connections',
  description: 'Operator review of automated financial connection records.',
  robots: { index: false, follow: false },
}

export default async function FinancialConnectionsPage() {
  await requireOperatorPage()

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-3xl font-bold text-civic-navy">Financial Connections</h1>
      <p className="text-slate-600 mt-3 mb-6 max-w-3xl">
        Automated matches between agenda text and financial records, for operator review.
        A match is a lead to check against the original records. It does not establish a
        conflict of interest, wrongdoing, or how an official voted.
      </p>
      <FinancialConnectionsAllTable />
      <Link href="/about" className="mt-6 inline-flex min-h-11 items-center text-civic-navy underline">
        Sources and methodology
      </Link>
    </div>
  )
}
