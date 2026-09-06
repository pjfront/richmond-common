import { describe, expect, it } from 'vitest'
import { buildRaceNarrative } from './electionNarrative'
import type { CandidateFundraisingDetail } from './types'
import { emptyMatrix } from './contributionBuckets'

function candidate(name: string, raised: number): CandidateFundraisingDetail {
  return {
    id: name, candidate_name: name, office_sought: 'Mayor', is_incumbent: false,
    status: 'qualified', total_raised: raised, donor_count: 161, contribution_count: 198,
    avg_contribution: 370, largest_contribution: 9140, smallest_contribution: 1,
    committee_id: null, official_id: null, top_donors: [], contribution_matrix: emptyMatrix(),
    bucket_grid_consistent: false, earliest_contribution: null, latest_contribution: null,
    lifetime_raised: raised,
  }
}

describe('race narrative source coverage', () => {
  const candidates = [candidate('Ahmad J. Anderson', 73300), candidate('Claudia Jimenez', 60365), candidate('Other candidate', 10)]

  it.each([1, 2, 3])('keeps the %s-candidate roster without financial claims when coverage is unresolved', (count) => {
    const race = candidates.slice(0, count)
    const before = structuredClone(race)
    const narrative = buildRaceNarrative('Mayor', race, { includeFundraising: false })
    for (const candidate of race) expect(narrative).toContain(candidate.candidate_name)
    expect(narrative).not.toMatch(/raised|donor|\$|follows with/)
    expect(race).toEqual(before)
  })

  it('preserves incumbent context without treating unavailable funding as zero', () => {
    const narrative = buildRaceNarrative('Mayor', [{ ...candidates[0], is_incumbent: true }, candidates[1]], { includeFundraising: false })
    expect(narrative).toBe('Ahmad J. Anderson (incumbent) faces Claudia Jimenez.')
  })

  it('leaves ordinary races unchanged when no coverage override applies', () => {
    expect(buildRaceNarrative('Mayor', candidates)).toContain('has raised the most — $73,300 from 161 donors')
    expect(buildRaceNarrative('Mayor', [])).toBeNull()
  })
})
