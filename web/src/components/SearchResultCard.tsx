import Link from 'next/link'
import type { SearchResult } from '@/lib/types'

const TYPE_BADGES: Record<string, { label: string; className: string }> = {
  agenda_item: { label: 'Agenda Item', className: 'bg-civic-navy/10 text-civic-navy' },
  official: { label: 'Council Member', className: 'bg-civic-amber/10 text-civic-amber' },
  vote_explainer: { label: 'Vote', className: 'bg-vote-aye/10 text-vote-aye' },
  meeting: { label: 'Meeting', className: 'bg-slate-100 text-slate-700' },
}

function MetadataLine({ result }: { result: SearchResult }) {
  const meta = result.metadata
  const parts: string[] = []

  if (meta.meeting_date) {
    parts.push(
      new Date(meta.meeting_date as string).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
    )
  }
  if (meta.category) parts.push(meta.category as string)
  if (meta.item_number) parts.push(`Item ${meta.item_number}`)
  if (meta.role) parts.push(meta.role as string)
  if (meta.is_current === false) parts.push('Former')
  if (meta.commission_type) parts.push(meta.commission_type as string)

  if (parts.length === 0) return null
  return <p className="text-xs text-slate-400 mt-1">{parts.join(' · ')}</p>
}

export default function SearchResultCard({ result }: { result: SearchResult }) {
  const badge = TYPE_BADGES[result.result_type] ?? TYPE_BADGES.agenda_item

  return (
    <Link
      href={result.url_path}
      className="block bg-white rounded-lg border border-slate-200 p-4 hover:border-civic-navy-light transition-colors"
    >
      <div className="flex items-start gap-2">
        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded shrink-0 ${badge.className}`}>
          {badge.label}
        </span>
        <h3 className="text-sm font-medium text-slate-800 leading-snug">{result.title}</h3>
      </div>
      {result.snippet && (
        <p
          className="text-sm text-slate-600 mt-2 leading-relaxed line-clamp-2"
          dangerouslySetInnerHTML={{ __html: result.snippet }}
        />
      )}
      <MetadataLine result={result} />
    </Link>
  )
}
