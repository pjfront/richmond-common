import type { Provenance } from '@/lib/types'
import { BioAttribution } from './SourceAttribution'

interface BioSummaryProps {
  bioSummary: string | null
  bioGeneratedAt: string | null
  bioModel: string | null
  bioProvenance: Provenance | null
  officialName: string
  meetingCount: number
}

/**
 * Council member bio summary card. Source attribution lives in
 * <BioAttribution>, which reads bio_summary_provenance to surface the
 * "official minutes" vs. "mixed (X minutes + Y transcript)" distinction
 * that audit row #5 (Entry 51) flagged as the highest-stakes
 * dishonest-attribution risk in the catalog.
 */
export default function BioSummary({
  bioSummary,
  bioGeneratedAt,
  bioModel: _bioModel,
  bioProvenance,
  officialName,
  meetingCount,
}: BioSummaryProps) {
  if (!bioSummary) return null

  return (
    <section className="mb-8">
      <h2 className="text-xl font-semibold text-slate-800 mb-3">Summary</h2>
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <p className="text-sm text-slate-800 leading-relaxed">{bioSummary}</p>
        <hr className="my-3 border-slate-100" />
        <p className="text-xs text-slate-400 leading-relaxed">
          <BioAttribution
            p={bioProvenance}
            officialName={officialName}
            meetingCount={meetingCount}
            generatedAt={bioGeneratedAt}
          />
        </p>
      </div>
    </section>
  )
}
