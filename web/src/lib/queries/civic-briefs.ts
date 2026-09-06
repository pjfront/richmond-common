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
