import CandidateCard, { type CandidateFinanceCoverageById, type CandidateIdentity } from './CandidateCard'

interface RaceSectionProps {
  office: string
  candidates: CandidateIdentity[]
  isHeroRace?: boolean
  id: string
  electionSlug?: string
  financeCoverage?: CandidateFinanceCoverageById
}

/** A candidate roster is independent of the completeness of its money records. */
export default function RaceSection({ office, candidates, id, electionSlug, financeCoverage = {} }: RaceSectionProps) {
  const ordered = [...candidates].sort((a, b) => a.candidate_name.localeCompare(b.candidate_name))
  return <section id={id} aria-labelledby={`${id}-heading`} className="mb-8 scroll-mt-20">
    <h2 id={`${id}-heading`} className="mb-3 text-xl font-semibold text-civic-navy">{office}</h2>
    <div className="space-y-3">
      {ordered.map(candidate => <CandidateCard key={candidate.id} candidate={candidate} electionSlug={electionSlug} financeCoverage={financeCoverage[candidate.id]} />)}
    </div>
  </section>
}
