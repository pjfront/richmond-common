export type CampaignEntityDataFailure = 'query-error' | 'incomplete'

/**
 * A campaign-entity directory must not turn a failed or truncated Supabase
 * response into a public "no activity" claim.
 */
export class CampaignEntityDataError extends Error {
  readonly failure: CampaignEntityDataFailure

  constructor(failure: CampaignEntityDataFailure, message: string) {
    super(message)
    this.name = 'CampaignEntityDataError'
    this.failure = failure
  }
}

/**
 * Proves that one bounded PostgREST response is complete. `count: 'exact'`
 * travels with the existing select, so this adds no database round trip.
 */
export function completeCampaignEntityRows<T>({
  dataset,
  data,
  error,
  count,
  maximumRows,
}: {
  dataset: string
  data: T[] | null
  error: unknown
  count: number | null
  maximumRows: number
}): T[] {
  if (error) {
    console.error(`${dataset} query failed:`, error)
    throw new CampaignEntityDataError(
      'query-error',
      `${dataset} could not be loaded.`,
    )
  }

  if (count === null) {
    throw new CampaignEntityDataError(
      'incomplete',
      `${dataset} did not return an exact row count.`,
    )
  }

  const rows = data ?? []
  if (count >= maximumRows || rows.length !== count) {
    throw new CampaignEntityDataError(
      'incomplete',
      `${dataset} returned ${rows.length.toLocaleString('en-US')} of ${count.toLocaleString('en-US')} rows.`,
    )
  }

  return rows
}

/**
 * Opt-in bridge for shared legacy queries. The repaired directories request a
 * completeness proof; unrelated profile/index callers retain their existing
 * empty fallback until they are migrated deliberately.
 */
export function campaignEntityRows<T>({
  requireComplete,
  ...response
}: Parameters<typeof completeCampaignEntityRows<T>>[0] & {
  requireComplete: boolean
}): T[] {
  if (requireComplete) return completeCampaignEntityRows(response)
  if (response.error) return []
  return response.data ?? []
}
