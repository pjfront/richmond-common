import type { Column } from '@tanstack/react-table'

interface SortableHeaderProps<T> {
  column: Column<T, unknown>
  label: string
  className?: string
}

export default function SortableHeader<T>({ column, label, className = '' }: SortableHeaderProps<T>) {
  const sorted = column.getIsSorted()
  return (
    <th
      className={`py-2 pr-3 font-medium text-slate-600 cursor-pointer select-none hover:text-civic-navy ${className}`}
      onClick={column.getToggleSortingHandler()}
    >
      {label}
      {sorted === 'asc' && ' \u2191'}
      {sorted === 'desc' && ' \u2193'}
      {!sorted && ' \u2195'}
    </th>
  )
}
