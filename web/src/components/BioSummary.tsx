interface BioSummaryProps {
  bioSummary: string | null
  bioGeneratedAt: string | null
  bioModel: string | null
  officialName: string
  meetingCount: number
}

export default function BioSummary({
  bioSummary,
  bioGeneratedAt,
  bioModel,
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
          This summary was auto-generated based on {officialName}&apos;s voting record
          across {meetingCount} meetings. It reflects patterns in official vote data,
          not editorial judgment.
          <br />
          Data sources: City of Richmond certified meeting minutes
          {bioGeneratedAt && (
            <>
              <br />
              Last updated: {new Date(bioGeneratedAt).toLocaleDateString()}
            </>
          )}
        </p>
      </div>
    </section>
  )
}
