import type { Metadata } from 'next'
import { getPublicRecordsStats, getDepartmentCompliance, getRecentRequests } from '@/lib/queries'
import ComplianceStats from '@/components/ComplianceStats'
import DepartmentBreakdown from '@/components/DepartmentBreakdown'
import RecentRequests from '@/components/RecentRequests'
import LastUpdated from '@/components/LastUpdated'

export const revalidate = 3600 // Revalidate every hour

export const metadata: Metadata = {
  title: 'Public Records',
  description: 'CPRA compliance dashboard — track Richmond public records request response times and department performance.',
}

const EMPTY_STATS = { totalRequests: 0, avgResponseDays: 0, onTimeRate: 0, currentlyOverdue: 0 }

export default async function PublicRecordsPage() {
  // Gracefully handle missing table (migration 003 may not be run yet)
  let stats = EMPTY_STATS
  let departments: Awaited<ReturnType<typeof getDepartmentCompliance>> = []
  let recentRequests: Awaited<ReturnType<typeof getRecentRequests>> = []
  try {
    ;[stats, departments, recentRequests] = await Promise.all([
      getPublicRecordsStats(),
      getDepartmentCompliance(),
      getRecentRequests(20),
    ])
  } catch (e) {
    console.error('Failed to fetch public records data:', e)
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-3xl font-bold text-civic-navy">Public Records Compliance</h1>
      <p className="text-slate-600 mt-2">
        Tracking Richmond&apos;s response to California Public Records Act (CPRA) requests.
        Under CPRA, agencies must respond within 10 calendar days.
      </p>

      {/* Stats bar */}
      <section className="mt-8">
        <ComplianceStats stats={stats} />
      </section>

      {/* Department breakdown */}
      <section className="mt-10">
        <h2 className="text-xl font-semibold text-slate-800 mb-4">Department Breakdown</h2>
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <DepartmentBreakdown departments={departments} />
        </div>
      </section>

      {/* Recent requests */}
      <section className="mt-10">
        <h2 className="text-xl font-semibold text-slate-800 mb-4">Recent Requests</h2>
        <RecentRequests requests={recentRequests} />
      </section>

      {/* Methodology note */}
      <section className="mt-10 bg-slate-50 rounded-lg p-6 border border-slate-200">
        <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">About This Data</h3>
        <p className="text-sm text-slate-600 mt-2">
          Data is scraped from Richmond&apos;s{' '}
          <a
            href="https://cityofrichmondca.nextrequest.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-civic-navy hover:underline"
          >
            NextRequest portal
          </a>
          . &quot;On-time&quot; means the request was closed within 10 calendar days of submission
          (the CPRA statutory deadline). Some requests may have legitimate extensions.
          This dashboard tracks response patterns, not legal compliance determinations.
        </p>
      </section>

      <LastUpdated />
    </div>
  )
}
