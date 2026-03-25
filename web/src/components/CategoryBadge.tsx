const categoryColors: Record<string, string> = {
  // Backend categories (authoritative, match AgendaCategory enum)
  zoning: 'bg-lime-100 text-lime-800',
  budget: 'bg-green-100 text-green-800',
  housing: 'bg-blue-100 text-blue-800',
  public_safety: 'bg-red-100 text-red-800',
  environment: 'bg-emerald-100 text-emerald-800',
  infrastructure: 'bg-orange-100 text-orange-800',
  personnel: 'bg-pink-100 text-pink-800',
  contracts: 'bg-stone-100 text-stone-800',
  governance: 'bg-purple-100 text-purple-800',
  proclamation: 'bg-violet-100 text-violet-800',
  litigation: 'bg-rose-100 text-rose-800',
  other: 'bg-slate-100 text-slate-600',
  appointments: 'bg-sky-100 text-sky-800',
  // Forward-looking (zero-cost future-proofing)
  land_use: 'bg-amber-100 text-amber-800',
  economic_development: 'bg-teal-100 text-teal-800',
  health: 'bg-cyan-100 text-cyan-800',
  education: 'bg-indigo-100 text-indigo-800',
  transportation: 'bg-yellow-100 text-yellow-800',
  consent: 'bg-slate-100 text-slate-600',
  ceremonial: 'bg-violet-100 text-violet-800',
  procedural: 'bg-gray-100 text-gray-500',
}

const categoryLabels: Record<string, string> = {
  other: 'Miscellaneous',
}

export function formatCategory(cat: string): string {
  if (categoryLabels[cat]) return categoryLabels[cat]
  return cat.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

interface CategoryBadgeProps {
  category: string | null
  onClick?: (category: string) => void
  active?: boolean
}

export default function CategoryBadge({ category, onClick, active }: CategoryBadgeProps) {
  if (!category || category === 'other') return null

  const colorClass = categoryColors[category] ?? 'bg-slate-100 text-slate-600'
  const activeClass = active ? 'ring-2 ring-offset-1 ring-civic-navy' : ''
  const clickClass = onClick ? 'cursor-pointer hover:ring-1 hover:ring-slate-300' : ''

  function handleClick(e: React.MouseEvent) {
    if (!onClick || !category) return
    e.stopPropagation()
    onClick(category)
  }

  return (
    <span
      role={onClick ? 'button' : undefined}
      onClick={onClick ? handleClick : undefined}
      className={`inline-block text-xs font-medium px-2 py-0.5 rounded ${colorClass} ${activeClass} ${clickClass}`}
    >
      {formatCategory(category)}
    </span>
  )
}
