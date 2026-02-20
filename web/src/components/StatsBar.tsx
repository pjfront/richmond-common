interface StatItem {
  label: string
  value: number
}

function formatNumber(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return n.toLocaleString()
}

export default function StatsBar({ stats }: { stats: StatItem[] }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
      {stats.map((s) => (
        <div
          key={s.label}
          className="bg-white rounded-lg border border-slate-200 p-4 text-center"
        >
          <p className="text-2xl font-bold text-civic-navy">{formatNumber(s.value)}</p>
          <p className="text-xs text-slate-500 mt-1">{s.label}</p>
        </div>
      ))}
    </div>
  )
}
