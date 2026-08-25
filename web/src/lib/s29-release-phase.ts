/**
 * Source-controlled S29 release boundary.
 *
 * Keep this false through the 14 complete UTC-day baseline. The treatment
 * release changes this value in a reviewed commit so public SEO, structured
 * data, and expanded sitemap discovery cannot turn on through environment
 * drift or a control-plane edit.
 */
export const S29_PUBLIC_TREATMENT_ENABLED: boolean = false
