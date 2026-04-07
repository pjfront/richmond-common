'use client'

interface CouncilMember {
  district: string
  name: string
}

interface DistrictSelectorProps {
  selectedDistricts: string[]
  onChange: (districts: string[]) => void
  councilMembers?: CouncilMember[]
}

const DISTRICTS = ['1', '2', '3', '4', '5', '6']

export default function DistrictSelector({ selectedDistricts, onChange, councilMembers }: DistrictSelectorProps) {
  const selected = new Set(selectedDistricts)
  const memberMap = new Map(councilMembers?.map((m) => [m.district, m.name]) ?? [])

  function toggle(district: string) {
    const next = new Set(selected)
    if (next.has(district)) next.delete(district)
    else next.add(district)
    onChange(Array.from(next))
  }

  return (
    <div>
      <h4 className="text-sm font-semibold text-civic-navy mb-3">Your district</h4>
      <p className="text-xs text-slate-500 mb-3">
        Get updates on items affecting your part of Richmond.
      </p>

      <div className="grid grid-cols-2 gap-1.5">
        {DISTRICTS.map((d) => {
          const isSelected = selected.has(d)
          const member = memberMap.get(d)
          return (
            <button
              key={d}
              type="button"
              role="switch"
              aria-checked={isSelected}
              aria-label={`Follow District ${d}${member ? `, ${member}` : ''}`}
              onClick={() => toggle(d)}
              className={`flex items-center gap-2 px-3 py-2 rounded-md text-left transition-colors text-sm ${
                isSelected
                  ? 'bg-civic-navy/10 text-civic-navy'
                  : 'bg-white text-slate-600 hover:bg-slate-50'
              }`}
            >
              <span
                className={`flex-shrink-0 w-4 h-4 rounded-sm border transition-colors ${
                  isSelected
                    ? 'bg-civic-navy border-civic-navy'
                    : 'border-slate-300'
                }`}
              >
                {isSelected && (
                  <svg viewBox="0 0 16 16" className="w-4 h-4 text-white" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <path d="M4 8l3 3 5-5" />
                  </svg>
                )}
              </span>
              <span>
                <span className={`font-medium ${isSelected ? 'text-civic-navy' : 'text-civic-slate'}`}>
                  District {d}
                </span>
                {member && (
                  <span className="block text-xs text-slate-400 leading-tight">
                    {member}
                  </span>
                )}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
