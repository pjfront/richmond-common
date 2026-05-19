/**
 * Queries module barrel.
 *
 * Phase 2.4 of the 2026-05-09 re-architecture plan: the original
 * 5,607-LOC queries.ts is now split by domain. Callers continue to
 * `import { ... } from '@/lib/queries'` — this barrel re-exports
 * everything from the per-domain modules.
 *
 * When adding a new query function, put it in the domain file it
 * belongs to (or create a new domain file and add an `export *` line
 * below). Do NOT add function definitions to this barrel — they
 * belong with their domain so file sizes stay reviewable.
 */
export * from './_shared'
export * from './meetings'
export * from './council'
export * from './conflicts'
export * from './donors'
export * from './public_records'
export * from './commissions'
export * from './topics'
export * from './search'
export * from './influence'
export * from './elections'
export * from './pacs'
