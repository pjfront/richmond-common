import { unstable_cache } from 'next/cache'
import { supabase } from '@/lib/supabase'

export interface PublicBrief {
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

/** Direct email links check the current publication, outside the six-item feed
 * and its cache. A withdrawn or superseded publication is never substituted. */
export async function getPublishedCivicBriefVersion(id: string, version: string | string[] | undefined, published: string | string[] | undefined): Promise<(PublicBrief & { subject_key: string }) | null> {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)
    || typeof version !== 'string' || !/^[1-9]\d*$/.test(version) || !Number.isSafeInteger(Number(version))
    || typeof published !== 'string' || !published || !Number.isFinite(Date.parse(published))) return null
  const { data, error } = await supabase.from('civic_brief_candidates')
    .select('id,subject_key,title,body,sources,content_version,published_at')
    .eq('id', id).eq('status', 'published').eq('content_version', Number(version))
    // Preserve PostgreSQL microseconds; Date.toISOString would truncate them.
    .eq('published_at', published).maybeSingle()
  if (error) throw new Error('Reviewed update unavailable')
  return data as unknown as (PublicBrief & { subject_key: string }) | null
}
