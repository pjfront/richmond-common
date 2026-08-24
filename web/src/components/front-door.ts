import type { FrontDoorElection, FrontDoorMeeting } from '@/lib/queries/front-door'

type SourceTier = 1 | 2 | 3 | 4

interface FrontDoorSource {
  tier: SourceTier
  name: string
  url: string
  extractedAt: string
  freshnessLabel?: 'Updated' | 'Source recorded'
}

export interface FrontDoorCardContent {
  href: string
  eyebrow: string
  title: string
  description: string
  source: FrontDoorSource | null
}

function sourceTier(value: number): SourceTier | null {
  return value === 1 || value === 2 || value === 3 || value === 4
    ? value
    : null
}

function publicSourceName(source: string, tier: SourceTier): string {
  const trimmed = source.trim()
  const normalized = trimmed.toLowerCase()
  if (!trimmed || ['seed', 'manual', 'import'].includes(normalized)) {
    return tier === 1 ? 'Official election record' : 'Independent election source'
  }
  return trimmed
}

function titleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

function formatPublicDate(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

export function buildElectionFrontDoorCard(
  election: FrontDoorElection | null,
  slug: string | null,
): FrontDoorCardContent {
  const tier = election ? sourceTier(election.source_tier) : null
  if (!election || !slug || !tier) {
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
    title: election.election_name ?? `${year} ${titleCase(election.election_type)}`,
    description: formatPublicDate(election.election_date),
    source: {
      tier,
      name: publicSourceName(election.source, tier),
      url: election.source_url,
      extractedAt: election.extracted_at,
      freshnessLabel: 'Source recorded',
    },
  }
}

export function buildMeetingFrontDoorCard(
  meeting: FrontDoorMeeting | null,
): FrontDoorCardContent {
  if (!meeting) {
    return {
      href: '/meetings',
      eyebrow: 'Meetings',
      title: 'Meeting records',
      description: 'Browse public meeting agendas and votes.',
      source: null,
    }
  }

  const bodyName = meeting.body_name ?? 'Richmond public body'
  const meetingType = meeting.meeting_type.toLowerCase() === 'regular'
    ? ''
    : `${titleCase(meeting.meeting_type.replaceAll('_', ' '))} `

  return {
    href: `/meetings/${meeting.id}`,
    eyebrow: 'Meeting',
    title: `${bodyName} ${meetingType}meeting`,
    description: formatPublicDate(meeting.meeting_date),
    source: {
      tier: meeting.source_tier,
      name: 'City of Richmond agenda',
      url: meeting.source_url,
      extractedAt: meeting.extracted_at,
    },
  }
}
