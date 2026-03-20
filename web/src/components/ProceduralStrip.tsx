import type { AgendaItemWithMotions } from '@/lib/types'

interface ProceduralStripProps {
  items: AgendaItemWithMotions[]
}

/**
 * Near-invisible timeline of procedural items.
 * Call to order, roll call, adjournment — minimal visual weight.
 */
export default function ProceduralStrip({ items }: ProceduralStripProps) {
  if (items.length === 0) return null

  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400 py-2 border-t border-slate-100 mt-4">
      {items.map(item => (
        <span key={item.id} className="flex items-center gap-1">
          <span className="text-[10px] font-mono">{item.item_number}</span>
          <span>{item.title}</span>
        </span>
      ))}
    </div>
  )
}
