import CategoryBadge from './CategoryBadge'

interface CategoryBreakdownProps {
  categories: { category: string; count: number }[]
  totalVotes: number
}

export default function CategoryBreakdown({ categories, totalVotes }: CategoryBreakdownProps) {
  if (categories.length === 0) return null

  return (
    <section className="mb-8">
      <h2 className="text-xl font-semibold text-slate-800 mb-3">
        Voting by Topic
      </h2>
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <div className="space-y-3">
          {categories.map((cat) => {
            const pct = totalVotes > 0 ? Math.round((cat.count / totalVotes) * 100) : 0
            return (
              <div key={cat.category} className="flex items-center gap-3">
                <div className="w-28 shrink-0">
                  <CategoryBadge category={cat.category} />
                </div>
                <div className="flex-1">
                  <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-civic-navy rounded-full"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
                <span className="text-sm text-slate-600 w-16 text-right">
                  {cat.count} ({pct}%)
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
