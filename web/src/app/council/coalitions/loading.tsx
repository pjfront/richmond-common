export default function CoalitionsLoading() {
  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="h-9 w-64 bg-slate-200 rounded animate-pulse mb-2" />
      <div className="h-5 w-full max-w-xl bg-slate-100 rounded animate-pulse mb-8" />

      {/* Stat cards skeleton */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="bg-white rounded-lg border border-slate-200 p-4">
            <div className="h-8 w-16 bg-slate-200 rounded animate-pulse mb-2" />
            <div className="h-4 w-24 bg-slate-100 rounded animate-pulse" />
          </div>
        ))}
      </div>

      {/* Matrix skeleton */}
      <div className="mb-10">
        <div className="h-6 w-48 bg-slate-200 rounded animate-pulse mb-1" />
        <div className="h-4 w-96 bg-slate-100 rounded animate-pulse mb-4" />
        <div className="bg-white rounded-lg border border-slate-200 p-6">
          <div className="h-64 bg-slate-50 rounded animate-pulse flex items-center justify-center">
            <p className="text-sm text-slate-400">Loading coalition analysis…</p>
          </div>
        </div>
      </div>

      {/* Blocs skeleton */}
      <div className="mb-10">
        <div className="h-6 w-36 bg-slate-200 rounded animate-pulse mb-1" />
        <div className="h-4 w-80 bg-slate-100 rounded animate-pulse mb-4" />
        <div className="space-y-3">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="bg-white rounded-lg border border-slate-200 p-4 h-20 animate-pulse" />
          ))}
        </div>
      </div>
    </div>
  )
}
