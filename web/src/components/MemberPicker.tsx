'use client'

interface MemberPickerProps {
  officials: Array<{ id: string; name: string }>
  selected: Set<string>
  onChange: (selected: Set<string>) => void
}

function lastName(full: string): string {
  return full.trim().split(/\s+/).pop() ?? full
}

export default function MemberPicker({ officials, selected, onChange }: MemberPickerProps) {
  const allSelected = officials.every((o) => selected.has(o.id))

  const toggle = (id: string) => {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    onChange(next)
  }

  const selectAll = () => {
    onChange(new Set(officials.map((o) => o.id)))
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-sm text-slate-600 mr-1">Show:</span>
      <button
        type="button"
        onClick={selectAll}
        disabled={allSelected}
        className={`text-xs font-medium px-3 py-1.5 rounded-full border transition-colors ${
          allSelected
            ? 'border-slate-200 bg-slate-50 text-slate-400 cursor-default'
            : 'border-civic-navy bg-civic-navy text-white hover:bg-civic-navy-light'
        }`}
      >
        All members
      </button>
      <span className="text-slate-300 text-xs px-1">·</span>
      {officials.map((o) => {
        const isSelected = selected.has(o.id)
        return (
          <button
            key={o.id}
            type="button"
            onClick={() => toggle(o.id)}
            aria-pressed={isSelected}
            className={`text-xs font-medium px-3 py-1.5 rounded-full border transition-colors ${
              isSelected
                ? 'border-civic-navy-light bg-civic-navy-light/10 text-civic-navy'
                : 'border-slate-200 bg-white text-slate-500 hover:border-slate-300 hover:text-slate-700'
            }`}
          >
            {lastName(o.name)}
          </button>
        )
      })}
    </div>
  )
}
