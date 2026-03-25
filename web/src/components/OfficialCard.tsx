import Link from 'next/link'
import type { Official } from '@/lib/types'
import { officialToSlug } from '@/lib/queries'

const roleBadge: Record<string, string> = {
  mayor: 'bg-civic-navy text-white',
  vice_mayor: 'bg-civic-navy-light text-white',
  council_member: 'bg-slate-100 text-slate-700',
}

function formatRole(role: string): string {
  return role.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function getInitials(name: string): string {
  return name
    .split(/\s+/)
    .map((w) => w[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase()
}

function formatTermEnd(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
}

/** Describe what the official is running for, if anything */
function candidacyLabel(
  official: Official,
  candidacy?: { office: string; electionDate: string },
): string | null {
  if (!candidacy) return null
  const elDate = new Date(candidacy.electionDate + 'T00:00:00')
  const monthYear = elDate.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
  // Cross-office candidacy (e.g., council member running for mayor)
  const currentRole = official.role === 'mayor' ? 'Mayor' : 'Council'
  const targetOffice = candidacy.office.includes('Mayor') ? 'Mayor' : candidacy.office
  if (currentRole === 'Mayor' && targetOffice === 'Mayor') {
    return `Running for re-election ${monthYear}`
  }
  if (targetOffice === 'Mayor') {
    return `Running for Mayor ${monthYear}`
  }
  return `Running for re-election ${monthYear}`
}

interface OfficialCardProps {
  official: Official
  voteCount?: number
  attendanceRate?: number
  candidacy?: { office: string; electionDate: string }
}

export default function OfficialCard({ official, voteCount, attendanceRate, candidacy }: OfficialCardProps) {
  const slug = officialToSlug(official.name)
  const runningFor = candidacyLabel(official, candidacy)

  return (
    <Link
      href={`/council/${slug}`}
      className="block bg-white rounded-lg border border-slate-200 p-4 hover:border-civic-navy-light hover:shadow-sm transition-all"
    >
      <div className="flex items-center gap-4">
        <div className="w-12 h-12 rounded-full bg-civic-navy/10 text-civic-navy flex items-center justify-center font-semibold text-sm shrink-0">
          {getInitials(official.name)}
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-slate-900">{official.name}</h3>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <span
              className={`text-xs font-medium px-2 py-0.5 rounded ${roleBadge[official.role] ?? 'bg-slate-100 text-slate-600'}`}
            >
              {formatRole(official.role)}
            </span>
            {official.seat && (
              <span className="text-xs font-medium text-slate-600">{official.seat}</span>
            )}
            {official.term_end && (
              <span className="text-xs text-slate-400">
                Term ends {formatTermEnd(official.term_end)}
              </span>
            )}
          </div>
          {runningFor && (
            <p className="text-xs font-medium text-civic-amber mt-1.5">
              {runningFor}
            </p>
          )}
          {(voteCount !== undefined || attendanceRate !== undefined) && (
            <div className="flex gap-4 mt-2 text-xs text-slate-500">
              {voteCount !== undefined && <span>{voteCount} votes tracked</span>}
              {attendanceRate !== undefined && (
                <span>{Math.round(attendanceRate * 100)}% attendance</span>
              )}
            </div>
          )}
        </div>
      </div>
    </Link>
  )
}
