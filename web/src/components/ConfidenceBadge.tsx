import { CONFIDENCE_TIER_1, CONFIDENCE_TIER_2 } from '@/lib/thresholds'

export default function ConfidenceBadge({ confidence }: { confidence: number }) {
  if (confidence >= CONFIDENCE_TIER_1) {
    return (
      <span className="inline-block text-xs font-semibold px-2 py-0.5 rounded bg-red-100 text-red-800 border border-red-200">
        Potential Conflict
      </span>
    )
  }
  if (confidence >= CONFIDENCE_TIER_2) {
    return (
      <span className="inline-block text-xs font-semibold px-2 py-0.5 rounded bg-amber-100 text-amber-800 border border-amber-200">
        Financial Connection
      </span>
    )
  }
  return (
    <span className="inline-block text-xs font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-500 border border-slate-200">
      Low Confidence
    </span>
  )
}
