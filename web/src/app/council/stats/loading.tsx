export default function StatsLoading() {
  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="h-9 w-48 bg-slate-200 rounded animate-pulse mb-2" />
      <div className="h-5 w-full max-w-xl bg-slate-100 rounded animate-pulse mb-8" />

      {/* Summary cards skeleton */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="bg-white rounded-lg border border-slate-200 p-4">
            <div className="h-8 w-16 bg-slate-200 rounded animate-pulse mb-2" />
            <div className="h-4 w-24 bg-slate-100 rounded animate-pulse" />
          </div>
        ))}
      </div>

      {/* Topic distribution table skeleton */}
      <div className="mb-10">
        <div className="h-6 w-44 bg-slate-200 rounded animate-pulse mb-1" />
        <div className="h-4 w-72 bg-slate-100 rounded animate-pulse mb-4" />
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <div className="space-y-3">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="flex gap-4">
                <div className="h-4 w-32 bg-slate-100 rounded animate-pulse" />
                <div className="h-4 w-16 bg-slate-100 rounded animate-pulse" />
                <div className="h-4 w-16 bg-slate-100 rounded animate-pulse" />
                <div className="h-4 w-20 bg-slate-100 rounded animate-pulse" />
              </div>
            ))}
          </div>
          <p className="text-sm text-slate-400 mt-4 text-center">Loading topic statistics…</p>
        </div>
      </div>

      {/* Controversy leaderboard skeleton */}
      <div className="mb-10">
        <div className="h-6 w-52 bg-slate-200 rounded animate-pulse mb-1" />
        <div className="h-4 w-96 bg-slate-100 rounded animate-pulse mb-4" />
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="bg-white rounded-lg border border-slate-200 p-4 h-16 animate-pulse" />
          ))}
        </div>
      </div>
    </div>
  )
}
