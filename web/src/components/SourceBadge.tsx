/**
 * SourceBadge — Design Rule C6
 *
 * Compact source attribution indicator showing:
 * - Source tier (1-4) with color coding
 * - Freshness timestamp ("Updated Mar 10, 2026" or "2 days ago")
 * - Bias disclosure for Tier 3 sources (mandatory, consistent)
 *
 * Required on every card, table row header, and detail section.
 *
 * Tier colors:
 *   Tier 1 (Official records): blue
 *   Tier 2 (Independent journalism): teal
 *   Tier 3 (Stakeholder communications): amber — always includes bias disclosure
 *   Tier 4 (Community/social): slate — always includes "not independently verified"
 */

interface SourceBadgeProps {
  /** Source tier (1-4) */
  tier: 1 | 2 | 3 | 4
  /** Source name (e.g., "Richmond Archive Center", "Tom Butt E-Forum") */
  source: string
  /** When the data was extracted/last updated (ISO string or Date) */
  extractedAt?: string | Date | null
  /** Bias disclosure for Tier 3 sources (e.g., "funded by Chevron Richmond") */
  biasDisclosure?: string
  /** Compact mode — shows only tier badge without freshness */
  compact?: boolean
}

const TIER_CONFIG = {
  1: { label: 'Official Record', classes: 'bg-blue-50 text-blue-700 border-blue-200' },
  2: { label: 'Independent Media', classes: 'bg-teal-50 text-teal-700 border-teal-200' },
  3: { label: 'Stakeholder', classes: 'bg-amber-50 text-amber-700 border-amber-200' },
  4: { label: 'Community', classes: 'bg-slate-100 text-slate-600 border-slate-200' },
} as const

function formatFreshness(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffDays === 0) return 'Updated today'
  if (diffDays === 1) return 'Updated yesterday'
  if (diffDays < 7) return `${diffDays} days ago`
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`

  return `Updated ${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}`
}

export default function SourceBadge({ tier, source, extractedAt, biasDisclosure, compact = false }: SourceBadgeProps) {
  const config = TIER_CONFIG[tier]

  // Tier 4 always gets the "not independently verified" note
  const disclosure = tier === 4
    ? 'Community source — not independently verified'
    : tier === 3
    ? biasDisclosure
      ? `${source} (${biasDisclosure})`
      : source
    : null

  if (compact) {
    return (
      <span
        className={`inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium rounded border ${config.classes}`}
        title={`Tier ${tier}: ${config.label} — ${source}${disclosure ? ` — ${disclosure}` : ''}`}
      >
        T{tier}
      </span>
    )
  }

  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] text-slate-500 flex-wrap">
      <span
        className={`inline-flex items-center gap-1 px-1.5 py-0.5 font-medium rounded border ${config.classes}`}
      >
        T{tier} · {config.label}
      </span>
      <span className="text-slate-400">
        {source}
        {disclosure && tier === 3 && (
          <span className="text-amber-600"> ({biasDisclosure})</span>
        )}
        {disclosure && tier === 4 && (
          <span className="italic"> — {disclosure}</span>
        )}
      </span>
      {extractedAt && (
        <span className="text-slate-400">· {formatFreshness(extractedAt)}</span>
      )}
    </span>
  )
}
