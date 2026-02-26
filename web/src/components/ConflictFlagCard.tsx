import Link from 'next/link'
import CategoryBadge from './CategoryBadge'
import ConfidenceBadge from './ConfidenceBadge'
import FeedbackButton from './FeedbackButton'

interface ConflictFlagDetail {
  id: string
  flag_type: string
  description: string
  confidence: number
  evidence: Record<string, unknown>[]
  legal_reference: string | null
  agenda_item_id: string | null
  official_id: string | null
  meeting_id: string | null
  agenda_item_title: string | null
  agenda_item_number: string | null
  agenda_item_category: string | null
  official_name: string | null
}

function formatFlagType(type: string): string {
  return type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export default function ConflictFlagCard({ flag }: { flag: ConflictFlagDetail }) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <ConfidenceBadge confidence={flag.confidence} />
            <span className="text-xs text-slate-400 font-medium">
              {formatFlagType(flag.flag_type)}
            </span>
          </div>
          {/* Temporal correlation callout */}
          {flag.flag_type === 'post_vote_donation' && flag.evidence?.[0] && (
            <div className="flex items-center gap-2 mt-1">
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800">
                {String((flag.evidence[0] as Record<string, unknown>).days_after_vote)} days after vote
              </span>
            </div>
          )}
          <p className="text-sm text-slate-800">{flag.description}</p>

          <div className="flex flex-wrap gap-3 mt-2 text-xs text-slate-500">
            {flag.agenda_item_title && (
              <span>
                Item {flag.agenda_item_number}: {flag.agenda_item_title}
              </span>
            )}
            <CategoryBadge category={flag.agenda_item_category} />
            {flag.official_name && (
              <span>Official: {flag.official_name}</span>
            )}
            {flag.legal_reference && (
              <span>Ref: {flag.legal_reference}</span>
            )}
          </div>

          {/* Evidence citations */}
          {flag.evidence.length > 0 && (
            <div className="mt-3 space-y-1">
              {flag.evidence.slice(0, 3).map((e, i) => (
                <p key={i} className="text-xs text-slate-400 italic">
                  {String((e as Record<string, unknown>).summary ?? (e as Record<string, unknown>).description ?? JSON.stringify(e)).slice(0, 200)}
                </p>
              ))}
            </div>
          )}
        </div>
        <div className="text-right shrink-0">
          <p className="text-xs text-slate-400">
            {Math.round(flag.confidence * 100)}%
          </p>
        </div>
      </div>

      <FeedbackButton flagId={flag.id} />

      {flag.meeting_id && (
        <div className="mt-3 pt-2 border-t border-slate-100">
          <Link
            href={`/meetings/${flag.meeting_id}`}
            className="text-xs text-civic-navy-light hover:text-civic-navy"
          >
            View meeting &rarr;
          </Link>
        </div>
      )}
    </div>
  )
}
