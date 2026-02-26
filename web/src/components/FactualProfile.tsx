interface FactualProfileProps {
  bioFactual: Record<string, unknown> | null
}

export default function FactualProfile({ bioFactual }: FactualProfileProps) {
  if (!bioFactual) return null

  const fields = [
    { label: 'Term', value: bioFactual.term_start ? `Since ${String(bioFactual.term_start).slice(0, 4)}` : null },
    { label: 'Votes Cast', value: bioFactual.vote_count },
    { label: 'Attendance', value: `${bioFactual.attendance_fraction} meetings (${bioFactual.attendance_rate})` },
    { label: 'Majority Alignment', value: bioFactual.majority_alignment_rate },
    { label: 'Sole Dissents', value: bioFactual.sole_dissent_count },
  ].filter((f) => f.value != null && f.value !== 0)

  const topCategories = (bioFactual.top_categories as { category: string; count: number }[]) ?? []

  return (
    <section className="mb-8">
      <h2 className="text-xl font-semibold text-slate-800 mb-3">Profile Summary</h2>
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <dl className="grid grid-cols-2 sm:grid-cols-3 gap-4">
          {fields.map((f) => (
            <div key={f.label}>
              <dt className="text-xs text-slate-500">{f.label}</dt>
              <dd className="text-sm font-medium text-slate-800">{String(f.value)}</dd>
            </div>
          ))}
        </dl>
        {topCategories.length > 0 && (
          <div className="mt-3 pt-3 border-t border-slate-100">
            <p className="text-xs text-slate-500 mb-1">Most Active In</p>
            <p className="text-sm text-slate-800">
              {topCategories.slice(0, 5).map((c) =>
                `${c.category.replace(/_/g, ' ')} (${c.count})`
              ).join(', ')}
            </p>
          </div>
        )}
        {typeof bioFactual.generated_at === 'string' && (
          <p className="text-xs text-slate-400 mt-3">
            Data as of {new Date(bioFactual.generated_at).toLocaleDateString()}
          </p>
        )}
      </div>
    </section>
  )
}
