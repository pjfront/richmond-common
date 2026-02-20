const categoryColors: Record<string, string> = {
  housing: 'bg-blue-100 text-blue-800',
  budget: 'bg-green-100 text-green-800',
  public_safety: 'bg-red-100 text-red-800',
  infrastructure: 'bg-orange-100 text-orange-800',
  environment: 'bg-emerald-100 text-emerald-800',
  governance: 'bg-purple-100 text-purple-800',
  land_use: 'bg-amber-100 text-amber-800',
  personnel: 'bg-pink-100 text-pink-800',
  economic_development: 'bg-teal-100 text-teal-800',
  health: 'bg-cyan-100 text-cyan-800',
  education: 'bg-indigo-100 text-indigo-800',
  transportation: 'bg-yellow-100 text-yellow-800',
  consent: 'bg-slate-100 text-slate-600',
  ceremonial: 'bg-violet-100 text-violet-800',
}

function formatCategory(cat: string): string {
  return cat.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export default function CategoryBadge({ category }: { category: string | null }) {
  if (!category) return null
  return (
    <span
      className={`inline-block text-xs font-medium px-2 py-0.5 rounded ${categoryColors[category] ?? 'bg-slate-100 text-slate-600'}`}
    >
      {formatCategory(category)}
    </span>
  )
}
