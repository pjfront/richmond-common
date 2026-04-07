'use client'

interface Candidate {
  id: string
  name: string
  office: string
  isIncumbent: boolean
  status: string
}

interface CandidatePreferencesProps {
  candidates: Candidate[]
  selectedCandidates: string[]
  onChange: (candidates: string[]) => void
}

export default function CandidatePreferences({ candidates, selectedCandidates, onChange }: CandidatePreferencesProps) {
  if (candidates.length === 0) return null

  const selected = new Set(selectedCandidates)

  // Group by office
  const byOffice = new Map<string, Candidate[]>()
  for (const c of candidates) {
    const group = byOffice.get(c.office) ?? []
    group.push(c)
    byOffice.set(c.office, group)
  }

  function toggle(id: string) {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    onChange(Array.from(next))
  }

  return (
    <div>
      <h4 className="text-sm font-semibold text-civic-navy mb-3">Candidates</h4>
      <p className="text-xs text-slate-500 mb-3">
        Follow candidates in the upcoming election.
      </p>

      <div className="space-y-4">
        {Array.from(byOffice.entries()).map(([office, officeCandidates]) => (
          <div key={office}>
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1.5">
              {office}
            </p>
            <div className="space-y-1.5">
              {officeCandidates.map((c) => {
                const isSelected = selected.has(c.id)
                const isWithdrawn = c.status === 'withdrawn'
                return (
                  <button
                    key={c.id}
                    type="button"
                    role="switch"
                    aria-checked={isSelected}
                    aria-label={`Follow ${c.name} for ${office}`}
                    disabled={isWithdrawn}
                    onClick={() => toggle(c.id)}
                    className={`w-full flex items-center gap-2 px-3 py-2 rounded-md text-left transition-colors text-sm ${
                      isWithdrawn
                        ? 'opacity-50 cursor-not-allowed bg-slate-50 text-slate-400'
                        : isSelected
                          ? 'bg-civic-navy/10 text-civic-navy'
                          : 'bg-white text-slate-600 hover:bg-slate-50'
                    }`}
                  >
                    <span
                      className={`flex-shrink-0 w-4 h-4 rounded-sm border transition-colors ${
                        isSelected && !isWithdrawn
                          ? 'bg-civic-navy border-civic-navy'
                          : 'border-slate-300'
                      }`}
                    >
                      {isSelected && !isWithdrawn && (
                        <svg viewBox="0 0 16 16" className="w-4 h-4 text-white" fill="none" stroke="currentColor" strokeWidth="2.5">
                          <path d="M4 8l3 3 5-5" />
                        </svg>
                      )}
                    </span>
                    <span className={`font-medium ${isSelected ? 'text-civic-navy' : 'text-civic-slate'}`}>
                      {c.name}
                    </span>
                    {c.isIncumbent && (
                      <span className="text-xs text-slate-400">(incumbent)</span>
                    )}
                    {isWithdrawn && (
                      <span className="text-xs text-slate-400">(withdrawn)</span>
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
