export default function ConfidenceBadge({ confidence }: { confidence: number }) {
  if (confidence >= 0.7) {
    return (
      <span className="inline-block text-xs font-semibold px-2 py-0.5 rounded bg-red-100 text-red-800 border border-red-200">
        Potential Conflict
      </span>
    )
  }
  if (confidence >= 0.5) {
    return (
      <span className="inline-block text-xs font-semibold px-2 py-0.5 rounded bg-amber-100 text-amber-800 border border-amber-200">
        Financial Connection
      </span>
    )
  }
  // Below 0.5 — should not normally be shown publicly
  return (
    <span className="inline-block text-xs font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-500 border border-slate-200">
      Low Confidence
    </span>
  )
}
