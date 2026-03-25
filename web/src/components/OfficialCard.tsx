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

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount)
}

interface OfficialCardProps {
  official: Official
  voteCount?: number
  attendanceRate?: number
  totalFundraising?: number
  donorCount?: number
}

export default function OfficialCard({ official, voteCount, attendanceRate, totalFundraising, donorCount }: OfficialCardProps) {
  const slug = officialToSlug(official.name)

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
              <span className="text-xs text-slate-400">{official.seat}</span>
            )}
          </div>

          {/* Stats row */}
          {(totalFundraising !== undefined || donorCount !== undefined || voteCount !== undefined || attendanceRate !== undefined) && (
            <div className="flex flex-wrap gap-x-5 gap-y-1 mt-2 text-sm text-slate-500">
              {totalFundraising !== undefined && totalFundraising > 0 && (
                <span>
                  <span className="font-medium text-slate-700">{formatCurrency(totalFundraising)}</span> raised
                </span>
              )}
              {donorCount !== undefined && donorCount > 0 && (
                <span>
                  <span className="font-medium text-slate-700">{donorCount}</span> donors
                </span>
              )}
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
