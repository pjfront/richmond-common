interface TopicLabelProps {
  label: string
  /** Compact size for tight spaces (calendar cells) */
  compact?: boolean
}

/**
 * Consistent topic label badge used across all meeting surfaces.
 *
 * Design: Monochrome slate treatment — topics are orientation signals,
 * not decorative elements. Color is reserved for interactive states
 * (the filter bar) and semantic meaning (vote outcomes, urgency).
 * This prevents the "confetti" problem where 12+ colored pills
 * create visual noise instead of clarity.
 */
export default function TopicLabel({ label, compact = false }: TopicLabelProps) {
  if (compact) {
    return (
      <span className="text-[10px] leading-tight px-1 rounded bg-slate-100 text-slate-500">
        {label}
      </span>
    )
  }

  return (
    <span className="inline-block text-xs font-medium px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200/60">
      {label}
    </span>
  )
}
