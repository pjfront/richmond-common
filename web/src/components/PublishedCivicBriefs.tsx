import { getPublishedCivicBriefs, type PublicBrief } from '@/lib/queries/civic-briefs'
import { formatCivicDate } from '@/lib/november-election'

export default async function PublishedCivicBriefs({ subjectKey }: { subjectKey: string }) {
  let briefs: PublicBrief[]
  try { briefs = await getPublishedCivicBriefs(subjectKey) } catch {
    return <p role="status" className="text-sm text-slate-600">Recent reviewed updates could not be loaded. The source-linked background on this page remains available.</p>
  }
  if (!briefs.length) return null
  return <section aria-label="Reviewed updates" className="mt-8">
    <h2 className="text-2xl font-semibold text-civic-navy">Reviewed updates</h2>
    <div className="mt-4 space-y-6">{briefs.map(brief => <article key={brief.id} className="border-l-4 border-civic-navy pl-5">
      <h3 className="text-lg font-semibold text-civic-navy">{brief.title}</h3>
      <p className="mt-1 text-sm text-slate-600">AI-written, operator-reviewed · published {formatCivicDate(brief.published_at)} · version {brief.content_version}</p>
      <p className="mt-3 whitespace-pre-line leading-relaxed text-slate-700">{brief.body}</p>
      <ul className="mt-3 space-y-1">{brief.sources.map(source => <li key={source.url} className="text-sm text-slate-600">
        <a href={source.url} className="inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4">{source.title}</a> · {source.source_tier === 1 ? 'Official record' : 'Independent journalism'}{source.source_date ? ` · ${formatCivicDate(source.source_date)}` : ' · source date not supplied'}
      </li>)}</ul>
    </article>)}</div>
  </section>
}
