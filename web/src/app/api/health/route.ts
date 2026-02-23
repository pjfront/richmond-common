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
]

async function tableExists(table: string): Promise<boolean> {
  const { error } = await supabase.from(table).select('*').limit(0)
  return !error
}

export async function GET() {
  const migrations: Record<string, MigrationResult> = {}
  let totalMissing = 0
  let coreMissing = false

  for (const group of MIGRATION_GROUPS) {
    const existing: string[] = []
    const missing: string[] = []

    for (const table of group.tables) {
      if (await tableExists(table)) {
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
        'Cache-Control': 'public, s-maxage=300, stale-while-revalidate=600',
      },
    },
  )
}
