import { unstable_cache } from 'next/cache'
import { supabase } from '@/lib/supabase'
import { formatCivicDate } from '@/lib/november-election'

interface PublicBrief {
  id: string
  title: string
  body: string
  sources: Array<{ url: string; title: string; source_tier: number; source_date: string | null }>
  content_version: number
  published_at: string
}

export const getPublishedCivicBriefs = unstable_cache(async (subjectKey: string): Promise<PublicBrief[]> => {
  const { data, error } = await supabase.from('civic_brief_candidates')
    .select('id,title,body,sources,content_version,published_at')
    .eq('subject_key', subjectKey).eq('status', 'published')
    .order('published_at', { ascending: false }).limit(6)
  if (error) throw new Error('Reviewed updates unavailable')
  return (data ?? []) as unknown as PublicBrief[]
}, ['published-civic-briefs-v1'], { revalidate: 900, tags: ['civic-briefs'] })

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
