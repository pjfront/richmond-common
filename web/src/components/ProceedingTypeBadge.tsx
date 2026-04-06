const LABELS: Record<string, string> = {
  resolution: 'Resolution',
  ordinance: 'Ordinance',
  contract: 'Contract',
  appropriation: 'Appropriation',
  appointment: 'Appointment',
  hearing: 'Hearing',
  proclamation: 'Proclamation',
  report: 'Report',
  censure: 'Censure',
  appeal: 'Appeal',
  consent: 'Consent',
  other: 'Other',
}

/**
 * Small badge showing the proceeding type classification.
 * Styled to sit alongside CategoryBadge and TopicLabel in
 * the item detail page header.
 */
export default function ProceedingTypeBadge({
  proceedingType,
}: {
  proceedingType: string
}) {
  const label = LABELS[proceedingType] ?? proceedingType
  return (
    <span className="text-xs text-slate-600 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
      {label}
    </span>
  )
}
