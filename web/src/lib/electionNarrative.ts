import type { CandidateFundraisingDetail } from './types'

/**
 * Build a 2-3 sentence narrative lede for a race section.
 *
 * Rules (from D6 / T4):
 * - Name the incumbent first
 * - Name the fundraising leader with total + donor count
 * - If a runner-up has raised >50% of the leader's total, name them too
 * - Never characterize ("leading", "outspent") — state facts only
 * - Maximum 3 sentences
 */
export function buildRaceNarrative(
  office: string,
  candidates: CandidateFundraisingDetail[],
): string | null {
  if (candidates.length === 0) return null

  const incumbent = candidates.find((c) => c.is_incumbent)
  const sorted = [...candidates].sort(
    (a, b) => b.total_raised - a.total_raised,
  )
  const withFunding = sorted.filter((c) => c.total_raised > 0)

  // Single candidate (unopposed)
  if (candidates.length === 1) {
    const c = candidates[0]
    const label = c.is_incumbent ? `${c.candidate_name} (incumbent)` : c.candidate_name
    const fundraising =
      c.total_raised > 0
        ? ` Committee has raised $${fmtNum(c.total_raised)} from ${c.donor_count} donor${c.donor_count !== 1 ? 's' : ''}.`
        : ''
    return `${label} is running unopposed.${fundraising}`
  }

  // Two candidates
  if (candidates.length === 2) {
    return buildTwoWayNarrative(candidates, incumbent, withFunding)
  }

  // Three or more candidates
  return buildMultiWayNarrative(candidates, incumbent, withFunding)
}

function buildTwoWayNarrative(
  candidates: CandidateFundraisingDetail[],
  incumbent: CandidateFundraisingDetail | undefined,
  withFunding: CandidateFundraisingDetail[],
): string {
  const [a, b] = incumbent
    ? [incumbent, candidates.find((c) => c !== incumbent)!]
    : candidates

  const aLabel = a.is_incumbent ? `${a.candidate_name} (incumbent)` : a.candidate_name
  const bLabel = b.is_incumbent ? `${b.candidate_name} (incumbent)` : b.candidate_name

  let sentence = `${aLabel} faces ${bLabel}.`

  if (withFunding.length === 2) {
    sentence += ` ${a.candidate_name} has raised $${fmtNum(a.total_raised)} from ${a.donor_count} donor${a.donor_count !== 1 ? 's' : ''}; ${b.candidate_name} has raised $${fmtNum(b.total_raised)} from ${b.donor_count} donor${b.donor_count !== 1 ? 's' : ''}.`
  } else if (withFunding.length === 1) {
    const funded = withFunding[0]
    sentence += ` ${funded.candidate_name} has raised $${fmtNum(funded.total_raised)} from ${funded.donor_count} donor${funded.donor_count !== 1 ? 's' : ''}.`
  }

  return sentence
}

function buildMultiWayNarrative(
  candidates: CandidateFundraisingDetail[],
  incumbent: CandidateFundraisingDetail | undefined,
  withFunding: CandidateFundraisingDetail[],
): string {
  const parts: string[] = []

  // Sentence 1: incumbent + challengers
  if (incumbent) {
    const challengers = candidates.filter((c) => c !== incumbent)
    const names = formatNameList(challengers.map((c) => c.candidate_name))
    parts.push(
      `${incumbent.candidate_name} is the incumbent, facing ${names}.`,
    )
  } else {
    const names = formatNameList(candidates.map((c) => c.candidate_name))
    parts.push(`${candidates.length} candidates are running: ${names}.`)
  }

  // Sentence 2: fundraising leader
  if (withFunding.length > 0) {
    const leader = withFunding[0]
    const leaderLabel = leader.is_incumbent ? leader.candidate_name : leader.candidate_name
    let fundraisingSentence = `${leaderLabel} has raised the most \u2014 $${fmtNum(leader.total_raised)} from ${leader.donor_count} donor${leader.donor_count !== 1 ? 's' : ''}.`

    // Sentence 3: runner-up if competitive (>50% of leader)
    if (withFunding.length >= 2) {
      const runnerUp = withFunding[1]
      if (runnerUp.total_raised > leader.total_raised * 0.5) {
        fundraisingSentence += ` ${runnerUp.candidate_name} follows with $${fmtNum(runnerUp.total_raised)}.`
      }
    }

    parts.push(fundraisingSentence)
  }

  return parts.join(' ')
}

/**
 * Build a one-line narrative summary for the election header.
 * Counts races by type and describes the ballot.
 */
export function buildElectionHeaderNarrative(
  races: Map<string, CandidateFundraisingDetail[]>,
): string {
  const total = races.size
  const contested: string[] = []
  const unopposed: string[] = []

  for (const [office, candidates] of races) {
    if (candidates.length > 1) {
      contested.push(office)
    } else {
      unopposed.push(office)
    }
  }

  const parts: string[] = []
  parts.push(
    `${total} race${total !== 1 ? 's' : ''} on the ballot.`,
  )

  if (contested.length > 0 && unopposed.length > 0) {
    const contestedNames = formatNameList(contested)
    const unopposedNames = formatNameList(unopposed)
    parts.push(
      `${contestedNames} ${contested.length === 1 ? 'is' : 'are'} contested; ${unopposedNames} ${unopposed.length === 1 ? 'is' : 'are'} unopposed.`,
    )
  }

  return parts.join(' ')
}

/** Format a number with comma separators, no decimals */
function fmtNum(n: number): string {
  return n.toLocaleString('en-US', { maximumFractionDigits: 0 })
}

/** "A, B, and C" formatting */
function formatNameList(names: string[]): string {
  if (names.length === 0) return ''
  if (names.length === 1) return names[0]
  if (names.length === 2) return `${names[0]} and ${names[1]}`
  return `${names.slice(0, -1).join(', ')}, and ${names[names.length - 1]}`
}
