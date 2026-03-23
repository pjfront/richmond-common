import type { OfficialComparativeStats } from '@/lib/queries'

interface ComparativeContextProps {
  stats: OfficialComparativeStats
  officialName: string
}

function ordinal(n: number): string {
  const s = ['th', 'st', 'nd', 'rd']
  const v = n % 100
  return n + (s[(v - 20) % 10] || s[v] || s[0])
}

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount)
}

export default function ComparativeContext({ stats, officialName }: ComparativeContextProps) {
  // Don't render if no contribution data at all
  if (stats.unique_donor_count === 0 && stats.total_contributions === 0) {
    return null
  }

  const { unique_donor_count, total_contributions, donor_count_rank, contributions_rank, total_officials } = stats

  // "more than X of Y" — officials ranked below this one
  const donorsBeatCount = total_officials - donor_count_rank

  return (
    <div
      className="mb-8 text-sm text-slate-500 space-y-1"
      role="region"
      aria-label={`Comparative campaign finance context for ${officialName}`}
    >
      {unique_donor_count > 0 && (
        <p>
          Received contributions from{' '}
          <span className="font-semibold text-civic-slate">
            {unique_donor_count.toLocaleString()} unique donor{unique_donor_count !== 1 ? 's' : ''}
          </span>
          {donorsBeatCount > 0 ? (
            <> — more than {donorsBeatCount} of {total_officials} council members</>
          ) : (
            <> — {ordinal(donor_count_rank)} of {total_officials} council members</>
          )}
        </p>
      )}
      {total_contributions > 0 && (
        <p>
          Total campaign fundraising:{' '}
          <span className="font-semibold text-civic-slate">
            {formatCurrency(total_contributions)}
          </span>
          {' — '}ranked {ordinal(contributions_rank)} of {total_officials}
        </p>
      )}
    </div>
  )
}
