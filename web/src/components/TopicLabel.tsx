import { topicLabelColor } from '@/lib/topic-label-colors'

interface TopicLabelProps {
  label: string
  /** Compact size for tight spaces (calendar cells) */
  compact?: boolean
}

/**
 * Consistent topic label badge used across all meeting surfaces.
 * Color is deterministic — same label always gets the same color.
 */
export default function TopicLabel({ label, compact = false }: TopicLabelProps) {
  const colorClass = topicLabelColor(label)

  if (compact) {
    return (
      <span className={`text-[10px] leading-tight px-1 rounded ${colorClass}`}>
        {label}
      </span>
    )
  }

  return (
    <span className={`inline-block text-xs font-medium px-2 py-0.5 rounded ${colorClass}`}>
      {label}
    </span>
  )
}
