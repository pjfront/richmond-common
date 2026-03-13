import { CONFIDENCE_STRONG, CONFIDENCE_MODERATE, CONFIDENCE_LOW } from '@/lib/thresholds'

/**
 * Three-tier confidence badge with green-yellow-red gradient.
 *
 * Strong  (>= 0.85): Red    — high-confidence pattern
 * Moderate (>= 0.70): Yellow — clear pattern with evidence
 * Low     (>= 0.50): Green  — possible pattern, limited evidence
 *
 * Optional tooltip shows exact confidence percentage on hover.
 */
export default function ConfidenceBadge({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100)

  if (confidence >= CONFIDENCE_STRONG) {
    return (
      <span
        className="inline-block text-xs font-semibold px-2 py-0.5 rounded bg-red-100 text-red-800 border border-red-200"
        title={`${pct}% confidence`}
      >
        Strong
      </span>
    )
  }
  if (confidence >= CONFIDENCE_MODERATE) {
    return (
      <span
        className="inline-block text-xs font-semibold px-2 py-0.5 rounded bg-yellow-100 text-yellow-800 border border-yellow-200"
        title={`${pct}% confidence`}
      >
        Moderate
      </span>
    )
  }
  if (confidence >= CONFIDENCE_LOW) {
    return (
      <span
        className="inline-block text-xs font-semibold px-2 py-0.5 rounded bg-green-100 text-green-800 border border-green-200"
        title={`${pct}% confidence`}
      >
        Low
      </span>
    )
  }
  // Below published threshold — should not normally render, but defensive
  return (
    <span
      className="inline-block text-xs font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-500 border border-slate-200"
      title={`${pct}% confidence`}
    >
      Internal
    </span>
  )
}
