import { NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'

/**
 * Migration health check endpoint.
 *
 * Probes expected tables via lightweight SELECTs to detect
 * which Supabase migrations have been applied. Returns overall
 * status: healthy | degraded | unhealthy.
 */

interface MigrationGroup {
  name: string
  tables: string[]
}

interface MigrationResult {
  applied: boolean
  tables?: string[]
  missing?: string[]
}

const MIGRATION_GROUPS: MigrationGroup[] = [
  {
    name: 'core_schema',
    tables: [
      'cities',
      'officials',
      'meetings',
      'agenda_items',
      'motions',
      'votes',
      'contributions',
      'documents',
      'conflict_flags',
    ],
  },
  {
    name: '001_cloud_pipeline',
    tables: ['scan_runs', 'data_sync_log'],
  },
  {
    name: '002_user_feedback',
    tables: ['user_feedback'],
  },
  {
    name: '003_nextrequest',
    tables: ['nextrequest_requests', 'nextrequest_documents'],
  },
  {
    name: '004_city_employees',
    tables: ['city_employees'],
  },
  {
    name: '005_commissions',
    tables: ['commissions', 'commission_members'],
  },
  {
    name: '035_bodies',
    tables: ['bodies'],
  },
  {
    name: '016_pending_decisions',
    tables: ['pending_decisions'],
  },
  {
    name: '040_entity_registry',
    tables: ['organizations', 'entity_links'],
  },
  {
    name: '082_neighborhood_councils',
    tables: ['neighborhood_councils'],
  },
]

/** Fetch the set of public-schema table names with one round-trip.
 *  Pre-2026-05 the route looped 18 separate `SELECT * LIMIT 0` probes
 *  per call (one per table), which contributed to the Supabase I/O
 *  quota pause. Calling the `list_public_tables` RPC is one round-trip
 *  total; if the RPC is missing on a given environment we fall back to
 *  the per-table probe and surface the migration as still healthy. */
async function fetchExistingTables(): Promise<Set<string> | null> {
  const { data, error } = await supabase.rpc('list_public_tables')
  if (error || !Array.isArray(data)) return null
  const names = new Set<string>()
  for (const row of data) {
    const name =
      typeof row === 'string'
        ? row
        : ((row as Record<string, unknown>).table_name as string | undefined)
    if (name) names.add(name)
  }
  return names
}

async function fallbackTableExists(table: string): Promise<boolean> {
  const { error } = await supabase.from(table).select('*').limit(0)
  return !error
}

export async function GET() {
  const migrations: Record<string, MigrationResult> = {}
  let totalMissing = 0
  let coreMissing = false

  const existingTables = await fetchExistingTables()

  for (const group of MIGRATION_GROUPS) {
    const existing: string[] = []
    const missing: string[] = []
    for (const table of group.tables) {
      const present = existingTables
        ? existingTables.has(table)
        : await fallbackTableExists(table)
      if (present) {
        existing.push(table)
      } else {
        missing.push(table)
      }
    }
    totalMissing += missing.length

    if (missing.length === 0) {
      migrations[group.name] = { applied: true, tables: existing }
    } else if (existing.length === 0) {
      migrations[group.name] = { applied: false, missing }
      if (group.name === 'core_schema') coreMissing = true
    } else {
      migrations[group.name] = { applied: false, tables: existing, missing }
      if (group.name === 'core_schema') coreMissing = true
    }
  }

  const status = totalMissing === 0 ? 'healthy' : coreMissing ? 'unhealthy' : 'degraded'

  return NextResponse.json(
    { status, migrations },
    {
      headers: {
        'Cache-Control': 'public, s-maxage=3600, stale-while-revalidate=7200',
      },
    },
  )
}
