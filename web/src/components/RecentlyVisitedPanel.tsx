'use client'

import Link from 'next/link'
import { useRecentlyVisited, type VisitedEntity } from '@/lib/useRecentlyVisited'
import type { EntityType } from '@/lib/types'

const ENTITY_ICONS: Record<EntityType, string> = {
  agenda_item: '\u{1F4C4}',
  official: '\u{1F464}',
  donor: '\u{1F3E2}',
  meeting: '\u{1F4C5}',
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text
  return text.slice(0, max - 1).trimEnd() + '\u2026'
}

function relativeTime(timestamp: number): string {
  const seconds = Math.floor((Date.now() - timestamp) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days === 1) return 'yesterday'
  if (days < 7) return `${days}d ago`
  return `${Math.floor(days / 7)}w ago`
}

function VisitEntry({ entity }: { entity: VisitedEntity }) {
  return (
    <Link
      href={entity.url}
      className="flex items-start gap-2 px-2 py-1.5 rounded hover:bg-slate-100 transition-colors group"
    >
      <span className="text-xs mt-0.5 shrink-0" aria-hidden="true">
        {ENTITY_ICONS[entity.type]}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-xs text-civic-slate leading-snug group-hover:text-civic-navy transition-colors">
          {truncate(entity.title, 40)}
        </p>
        <p className="text-[10px] text-slate-400 mt-0.5">
          {relativeTime(entity.visitedAt)}
        </p>
      </div>
    </Link>
  )
}

export default function RecentlyVisitedPanel() {
  const { visits, clearVisits } = useRecentlyVisited()

  if (visits.length === 0) return null

  return (
    <div className="border border-slate-200 rounded-lg bg-white">
      <div className="px-3 py-2 border-b border-slate-100">
        <h3 className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
          Recently Viewed
        </h3>
      </div>
      <div className="py-1">
        {visits.map((v) => (
          <VisitEntry key={`${v.type}-${v.id}`} entity={v} />
        ))}
      </div>
      <div className="px-3 py-2 border-t border-slate-100">
        <button
          onClick={clearVisits}
          className="text-[10px] text-slate-400 hover:text-civic-navy transition-colors"
        >
          Clear
        </button>
      </div>
    </div>
  )
}
