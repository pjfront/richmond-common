import type { PublicRecordsStats } from '@/lib/types'

/** Observed portal status and closure duration; no response/compliance inference. */
export default function ComplianceStats({ stats }: { stats: PublicRecordsStats }) {
  const cards = [
    { label: 'Indexed requests', value: stats.totalRequests.toLocaleString() },
    { label: 'Marked closed', value: stats.closedRequests.toLocaleString() },
    { label: 'Not marked closed', value: stats.notClosedRequests.toLocaleString() },
    { label: 'Average time to closure', value: stats.avgClosureDays === null ? 'Unavailable' : `${stats.avgClosureDays} days` },
  ]
  return (
    <div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {cards.map(({ label, value }) => (
          <div key={label} className="bg-white rounded-lg border border-slate-200 p-4 text-center">
            <div className="text-2xl font-bold text-civic-navy">{value}</div>
            <div className="text-sm text-slate-500 mt-1">{label}</div>
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-slate-500">
        Closure duration is based on {stats.closureTimingCount.toLocaleString()} marked-closed records with valid timing data.
        It does not measure the time to the city&apos;s first response or determine legal compliance.
      </p>
    </div>
  )
}
