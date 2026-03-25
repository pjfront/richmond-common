import Link from 'next/link'
import type { Official } from '@/lib/types'
import { officialToSlug } from '@/lib/queries'
import type { CycleFundraisingStats } from '@/lib/queries'

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

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount)
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

function FundraisingStat({ amount, label }: { amount: number; label: string }) {
  if (amount === 0) return null
  return (
    <div className="text-center">
      <p className="text-sm font-semibold text-slate-800">{formatCurrency(amount)}</p>
      <p className="text-[11px] text-slate-400 leading-tight">{label}</p>
    </div>
  )
}

interface OfficialCardProps {
  official: Official
  fundraisingStats?: CycleFundraisingStats
  candidacy?: { office: string; electionDate: string }
}

export default function OfficialCard({ official, fundraisingStats, candidacy }: OfficialCardProps) {
  const slug = officialToSlug(official.name)
  const allTime = fundraisingStats?.allTime
  const last = fundraisingStats?.lastElection
  const since = fundraisingStats?.sinceLastElection
  const hasAny = allTime && allTime.total > 0
  const runningFor = candidacyLabel(official, candidacy)

  return (
    <Link
      href={`/council/${slug}`}
      className="block bg-white rounded-lg border border-slate-200 p-5 hover:border-civic-navy-light hover:shadow-sm transition-all"
    >
      <div className="flex items-start gap-4">
        <div className="w-14 h-14 rounded-full bg-civic-navy/10 text-civic-navy flex items-center justify-center font-semibold text-base shrink-0">
          {getInitials(official.name)}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <h3 className="font-semibold text-lg text-slate-900">{official.name}</h3>
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

          {/* Fundraising stats — three columns */}
          {hasAny ? (
            <div className="flex items-start gap-6 mt-3 pt-3 border-t border-slate-100">
              <FundraisingStat amount={allTime.total} label="All time" />
              {last && <FundraisingStat amount={last.total} label={last.label} />}
              {since && <FundraisingStat amount={since.total} label="Since last election" />}
            </div>
          ) : fundraisingStats ? (
            <p className="text-xs text-slate-400 italic mt-2">No contributions on file</p>
          ) : null}
        </div>
      </div>
    </Link>
  )
}
