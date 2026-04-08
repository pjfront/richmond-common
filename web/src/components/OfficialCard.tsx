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
  candidacy?: { office: string; electionDate: string; isIncumbent?: boolean },
): string | null {
  if (!candidacy) return null
  const year = candidacy.electionDate.slice(0, 4)
  const isCrossOffice = official.role === 'mayor'
    ? !candidacy.office.includes('Mayor')
    : candidacy.office.includes('Mayor')
  if (isCrossOffice) {
    return `Running for ${candidacy.office} ${year}`
  }
  if (candidacy.isIncumbent) {
    return `Running for re-election ${year}`
  }
  return `Running for ${candidacy.office} ${year}`
}

interface OfficialCardProps {
  official: Official
  candidacy?: { office: string; electionDate: string; isIncumbent?: boolean }
}

export default function OfficialCard({ official, candidacy }: OfficialCardProps) {
  const slug = officialToSlug(official.name)
  const runningFor = candidacyLabel(official, candidacy)
  const showRoleBadge = official.role === 'mayor' || official.role === 'vice_mayor'

  return (
    <Link
      href={`/council/${slug}`}
      className="block bg-white rounded-lg border border-slate-200 p-4 hover:border-civic-navy-light hover:shadow-sm transition-all"
    >
      <div className="flex items-start gap-3">
        <div className="w-11 h-11 rounded-full bg-civic-navy/10 text-civic-navy flex items-center justify-center font-semibold text-sm shrink-0">
          {getInitials(official.name)}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-semibold text-base text-slate-900">{official.name}</h3>
            {showRoleBadge && (
              <span
                className={`text-xs font-medium px-2 py-0.5 rounded ${roleBadge[official.role]}`}
              >
                {formatRole(official.role)}
              </span>
            )}
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            {official.seat && !showRoleBadge && <>{official.seat} · </>}
            {official.term_end && <>Term ends {formatTermEnd(official.term_end)}</>}
          </p>
          {runningFor && (
            <p className="text-xs font-medium text-civic-amber mt-1">
              {runningFor}
            </p>
          )}
        </div>
      </div>
    </Link>
  )
}
