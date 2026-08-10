import type { Election } from '@/lib/types'

type SourceTier = 1 | 2 | 3 | 4

export interface ElectionFrontDoorCard {
  href: string
  eyebrow: string
  title: string
  description: string
  source: {
    tier: SourceTier
    name: string
    updatedAt: string
  } | null
}

function formatElectionType(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

function formatElectionDate(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

export function buildElectionFrontDoorCard(
  election: Election | null,
  slug: string | null,
): ElectionFrontDoorCard {
  if (!election || !slug) {
    return {
      href: '/elections',
      eyebrow: 'Elections',
      title: 'Election information',
      description: 'Find election dates, candidates, and voter information.',
      source: null,
    }
  }

  const year = election.election_date.slice(0, 4)
  return {
    href: `/elections/${slug}`,
    eyebrow: 'Current election',
    title: election.election_name ?? `${year} ${formatElectionType(election.election_type)}`,
    description: formatElectionDate(election.election_date),
    source: {
      tier: election.source_tier as SourceTier,
      name: election.source,
      updatedAt: election.updated_at,
    },
  }
}
