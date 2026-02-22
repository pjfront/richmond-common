import type { PublicRecordsStats } from '@/lib/types'

export default function ComplianceStats({ stats }: { stats: PublicRecordsStats }) {
  const cards = [
    { label: 'Total Requests', value: stats.totalRequests.toLocaleString(), color: 'text-civic-navy' },
    { label: 'Avg Response', value: `${stats.avgResponseDays} days`, color: stats.avgResponseDays <= 10 ? 'text-emerald-600' : 'text-amber-600' },
    { label: 'On-Time Rate', value: `${stats.onTimeRate}%`, color: stats.onTimeRate >= 80 ? 'text-emerald-600' : stats.onTimeRate >= 50 ? 'text-amber-600' : 'text-red-600' },
    { label: 'Currently Overdue', value: stats.currentlyOverdue.toString(), color: stats.currentlyOverdue === 0 ? 'text-emerald-600' : 'text-red-600' },
  ]

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {cards.map(({ label, value, color }) => (
        <div key={label} className="bg-white rounded-lg border border-slate-200 p-4 text-center">
          <div className={`text-2xl font-bold ${color}`}>{value}</div>
          <div className="text-sm text-slate-500 mt-1">{label}</div>
        </div>
      ))}
    </div>
  )
}
