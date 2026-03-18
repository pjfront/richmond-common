import type { NextRequestRequest } from '@/lib/types'

function statusBadge(status: string) {
  const lower = (status || '').toLowerCase()
  if (lower === 'completed' || lower === 'closed') {
    return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700">Completed</span>
  }
  if (lower.includes('progress') || lower === 'in_progress') {
    return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700">In Progress</span>
  }
  if (lower === 'overdue') {
    return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">Overdue</span>
  }
  return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600">{status}</span>
}

function daysElapsed(submittedDate: string | null, closedDate: string | null): string {
  if (closedDate) {
    const days = Math.floor(
      (new Date(closedDate).getTime() - new Date(submittedDate || closedDate).getTime()) /
      (1000 * 60 * 60 * 24)
    )
    return `${days}d to close`
  }
  if (submittedDate) {
    const days = Math.floor(
      (Date.now() - new Date(submittedDate).getTime()) / (1000 * 60 * 60 * 24)
    )
    return `${days}d elapsed`
  }
  return ''
}

export default function RecentRequests({ requests }: { requests: NextRequestRequest[] }) {
  if (requests.length === 0) {
    return <p className="text-slate-500">No CPRA requests found.</p>
  }

  return (
    <div className="space-y-3">
      {requests.map((r) => (
        <div
          key={r.id}
          className="bg-white rounded-lg border border-slate-200 p-4 hover:border-slate-300 transition-colors"
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-mono text-slate-400">{r.request_number}</span>
                {r.department && (
                  <span className="px-2 py-0.5 rounded text-xs bg-civic-navy/10 text-civic-navy font-medium">
                    {r.department}
                  </span>
                )}
              </div>
              <p className="text-sm text-slate-700 line-clamp-2">
                {r.request_text.slice(0, 120)}{r.request_text.length > 120 ? '...' : ''}
              </p>
            </div>
            <div className="flex flex-col items-end gap-1 shrink-0">
              {statusBadge(r.status)}
              <span className="text-xs text-slate-400">
                {daysElapsed(r.submitted_date, r.closed_date)}
              </span>
            </div>
          </div>
          {r.portal_url && (
            <a
              href={r.portal_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-civic-navy hover:underline mt-2 inline-block"
            >
              View on portal &rarr;
            </a>
          )}
        </div>
      ))}
    </div>
  )
}
