import type { Column } from '@tanstack/react-table'

interface CampaignEntitySortableHeaderProps<T> {
  column: Column<T, unknown>
  label: string
  className?: string
}

/** Accessible sort control scoped to the campaign-entity receipt tables. */
export default function CampaignEntitySortableHeader<T>({
  column,
  label,
  className = '',
}: CampaignEntitySortableHeaderProps<T>) {
  const sorted = column.getIsSorted()
  const direction = sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : 'not sorted'

  return (
    <button
      type="button"
      onClick={column.getToggleSortingHandler()}
      className={`inline-flex min-h-11 items-center gap-1 rounded-sm text-left hover:text-civic-navy focus:outline-none focus:ring-2 focus:ring-civic-navy focus:ring-offset-2 ${className}`}
      aria-label={`Sort by ${label}; currently ${direction}`}
    >
      {label}
      <span aria-hidden="true">
        {sorted === 'asc' ? '\u2191' : sorted === 'desc' ? '\u2193' : '\u2195'}
      </span>
    </button>
  )
}
