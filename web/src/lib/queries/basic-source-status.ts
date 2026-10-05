import { unstable_cache } from 'next/cache'
import { supabase } from '@/lib/supabase'
import { featureProfile, isLocalArchive } from '@/lib/feature-policy'
import { BASIC_SOURCE_FEATURES, basicSourceStatus, type BasicSourceStatus, type CoreProjectionStatusRow } from '@/lib/basic-source-status'

const readBasicSourceStatus = unstable_cache(async (): Promise<CoreProjectionStatusRow[]> => {
  const { data, error, count } = await supabase.from('core_projection_status')
    .select('feature,status,checked_at,source_scope', { count: 'exact' })
    .in('feature', [...BASIC_SOURCE_FEATURES]).order('feature').limit(2)
  if (error || !data || count == null || !Number.isInteger(count) || count < 0 || count > 2 || data.length !== count) {
    throw new Error('Source check metadata unavailable')
  }
  const rows = data as unknown as CoreProjectionStatusRow[]
  if (rows.some(row => !BASIC_SOURCE_FEATURES.includes(row.feature as typeof BASIC_SOURCE_FEATURES[number])) || new Set(rows.map(row => row.feature)).size !== rows.length) {
    throw new Error('Source check metadata outside the approved projection')
  }
  return rows
}, ['basic-source-status-v1'], { revalidate: 300, tags: ['basic-source-status'] })

/** Anon-only two-row projection; local archives never claim a fresh source check. */
export async function getBasicSourceRefreshStatus(): Promise<BasicSourceStatus | null> {
  if (featureProfile() !== 'basic_public' || isLocalArchive()) return null
  try {
    return basicSourceStatus(await readBasicSourceStatus())
  } catch {
    // Keep failed reads distinct from sources that have never been checked.
    return basicSourceStatus(null)
  }
}
