/**
 * Richmond Local Issue Type Definition
 *
 * As of S28.0 (2026-04-15), the `topics` database table is the single
 * source of truth for the topic taxonomy. This file no longer exports
 * a hardcoded `RICHMOND_LOCAL_ISSUES` constant or a client-side
 * `detectLocalIssues()` keyword matcher — both have been removed.
 *
 * Callers should now use:
 *   - `getTopicTaxonomy()` from `@/lib/queries` for the full list
 *     (returns `LocalIssue[]` mapped from the DB)
 *   - Server-side topic tagging via Python's `topic_tagger.tag_topics()`
 *     (runs at ingestion, persists to `item_topics` / `topic_news_articles`)
 *
 * This file now exists only as the TypeScript type definition shared
 * across components that accept the taxonomy as a prop.
 */

export interface LocalIssue {
  /** URL-safe slug, e.g. "chevron", "point-molate". Historically called `id`. */
  id: string
  /** The label Richmond residents would use, e.g. "Chevron & the Refinery". */
  label: string
  /** One-line context for tooltips and cards. */
  context: string
  /** Case-insensitive substring keywords matched against agenda/news text. */
  keywords: string[]
  /**
   * Legacy Tailwind color-class string, kept for schema parity with the
   * `topics.color_classes` column. New UI work should not rely on this
   * field — topic tags are no longer differentiated by chroma (D6 + C2
   * compliance). Left non-empty for downstream compatibility until all
   * call sites are migrated off.
   */
  color: string
}
