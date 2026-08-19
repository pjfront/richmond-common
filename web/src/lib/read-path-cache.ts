/**
 * Persistent read-path cache policy.
 *
 * Keep these values named and tested: they are operational choices, not
 * incidental implementation details. React's `cache()` only deduplicates one
 * render, while these reads need to avoid repeated Supabase work across
 * requests and ISR renders.
 */
export const OFFICIALS_CACHE_SECONDS = 24 * 60 * 60

/**
 * Similarity changes only when embeddings or agenda items change. Seven days
 * is the proposed November demand-test tradeoff; keeping it in one constant
 * makes the operator approval/change explicit before release.
 */
export const SIMILAR_ITEMS_CACHE_SECONDS = 7 * 24 * 60 * 60

export const MAX_SIMILAR_ITEMS = 10
