/**
 * EntityTypeIndicator — Design System Component (S14 A7)
 *
 * Visual differentiation for entity types across the influence map.
 * Color + icon per entity type reduces disorientation during
 * cross-entity navigation (Research D finding).
 *
 * Used inline with entity names on influence map pages.
 */

import type { EntityType } from '@/lib/types'

interface EntityTypeIndicatorProps {
  entityType: EntityType
  /** Show label text alongside icon */
  showLabel?: boolean
  /** Size variant */
  size?: 'sm' | 'md'
}

const ENTITY_TYPE_CONFIG: Record<EntityType, {
  label: string
  icon: string
  colorClass: string
}> = {
  agenda_item: {
    label: 'Agenda Item',
    icon: '📄',
    colorClass: 'text-green-700',
  },
  official: {
    label: 'Official',
    icon: '👤',
    colorClass: 'text-blue-700',
  },
  donor: {
    label: 'Donor',
    icon: '🏢',
    colorClass: 'text-orange-700',
  },
  meeting: {
    label: 'Meeting',
    icon: '📅',
    colorClass: 'text-slate-600',
  },
}

export default function EntityTypeIndicator({
  entityType,
  showLabel = false,
  size = 'sm',
}: EntityTypeIndicatorProps) {
  const config = ENTITY_TYPE_CONFIG[entityType]
  const sizeClass = size === 'sm' ? 'text-xs' : 'text-sm'

  return (
    <span
      className={`inline-flex items-center gap-1 ${sizeClass} ${config.colorClass}`}
      title={config.label}
    >
      <span aria-hidden="true" className={size === 'sm' ? 'text-[11px]' : 'text-sm'}>
        {config.icon}
      </span>
      {showLabel && (
        <span className="font-medium">{config.label}</span>
      )}
    </span>
  )
}
