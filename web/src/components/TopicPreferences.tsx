'use client'

import { RICHMOND_LOCAL_ISSUES } from '@/lib/local-issues'

interface TopicPreferencesProps {
  selectedTopics: string[]
  onChange: (topics: string[]) => void
}

// The Big Three get visual priority — these define Richmond politics
const BIG_THREE = new Set(['chevron', 'point_molate', 'rent_board'])

export default function TopicPreferences({ selectedTopics, onChange }: TopicPreferencesProps) {
  const selected = new Set(selectedTopics)
  const bigThree = RICHMOND_LOCAL_ISSUES.filter((i) => BIG_THREE.has(i.id))
  const others = RICHMOND_LOCAL_ISSUES.filter((i) => !BIG_THREE.has(i.id))

  function toggle(id: string) {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    onChange(Array.from(next))
  }

  return (
    <div>
      <h4 className="text-sm font-semibold text-civic-navy mb-3">Topics</h4>
      <p className="text-xs text-slate-500 mb-3">
        Choose the Richmond issues you want to hear about.
      </p>

      {/* Big Three — prominent */}
      <div className="space-y-1.5 mb-3">
        {bigThree.map((issue) => (
          <TopicRow
            key={issue.id}
            id={issue.id}
            label={issue.label}
            context={issue.context}
            checked={selected.has(issue.id)}
            onToggle={toggle}
          />
        ))}
      </div>

      {/* All other topics */}
      <div className="space-y-1.5">
        {others.map((issue) => (
          <TopicRow
            key={issue.id}
            id={issue.id}
            label={issue.label}
            context={issue.context}
            checked={selected.has(issue.id)}
            onToggle={toggle}
          />
        ))}
      </div>
    </div>
  )
}

function TopicRow({
  id,
  label,
  context,
  checked,
  onToggle,
}: {
  id: string
  label: string
  context: string
  checked: boolean
  onToggle: (id: string) => void
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={`Follow ${label}`}
      onClick={() => onToggle(id)}
      className={`w-full flex items-center gap-3 px-3 py-2 rounded-md text-left transition-colors text-sm ${
        checked
          ? 'bg-civic-navy/10 text-civic-navy'
          : 'bg-white text-slate-600 hover:bg-slate-50'
      }`}
    >
      <span
        className={`flex-shrink-0 w-4 h-4 rounded-sm border transition-colors ${
          checked
            ? 'bg-civic-navy border-civic-navy'
            : 'border-slate-300'
        }`}
      >
        {checked && (
          <svg viewBox="0 0 16 16" className="w-4 h-4 text-white" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M4 8l3 3 5-5" />
          </svg>
        )}
      </span>
      <span className="flex-1">
        <span className={`font-medium ${checked ? 'text-civic-navy' : 'text-civic-slate'}`}>
          {label}
        </span>
        <span className="block text-xs text-slate-400 leading-tight mt-0.5 line-clamp-1">
          {context}
        </span>
      </span>
    </button>
  )
}
