/**
 * Drift safeguard for `types.ts`.
 *
 * Every hand-curated interface in `types.ts` that mirrors a public-schema
 * table must anchor to the generated row type via
 *   `extends Omit<Tables<'tablename'>, ...>` (or `Tables<'tablename'>` alias).
 *
 * Without anchoring, a future migration that drops or renames a column
 * leaves the hand-rolled type stale and silent. With anchoring, the
 * `Omit<>` line fails to compile, forcing the type to be updated alongside
 * the migration. Combined with `schema-drift.yml` (which forces
 * `database.types.ts` to be regenerated on any migration touching the
 * schema), this makes drift a compile error rather than a runtime bug.
 *
 * If you intentionally want a freestanding interface (because the shape
 * isn't a 1:1 row type — e.g. a composite, a view, or a DTO), add the
 * interface name to EXEMPT_INTERFACES with a one-line reason.
 *
 * Detection: for each `export interface X`, derive candidate table names
 * from X (snake_case + simple pluralization). If any candidate matches a
 * real public table, the interface MUST reference `Tables<'tablename'>`
 * in its declaration. Otherwise it is freestanding.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'

// Interfaces that mirror a table name but legitimately should NOT anchor
// to Tables<>. Add with a one-line reason. Empty list is the goal.
const EXEMPT_INTERFACES = new Set<string>([
  // Seeded with interfaces still pending Phase 2.5 sweep. Removed
  // from this list as each is anchored in follow-up commits.
  'City',
  'Official',
  'MeetingAttendance',
  'AgendaItem',
  'Motion',
  'Vote',
  'Contribution',
  'Donor',
  'Committee',
  'ConflictFlag',
  'ClosedSessionItem',
  'PublicComment',
  'Body',
  'Commission',
  'CommissionMember',
  'Election',
  'ElectionCandidate',
  'CommunityComment',
  'EmailSubscriber',
  'EmailPreference',
  'NeighborhoodCouncil',
  'EconomicInterest',
  'UserFeedback',
  'PendingDecision',
  'FilingPeriodBriefing',
  'CommentTheme',
  'OperatorConfig',
])

// CamelCase → snake_case
function toSnake(name: string): string {
  return name
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/([A-Z]+)([A-Z][a-z])/g, '$1_$2')
    .toLowerCase()
}

// Candidate table names to test for a given interface name.
function tableCandidates(name: string): string[] {
  const snake = toSnake(name)
  const candidates = new Set<string>([snake])
  // Plural forms — Postgres tables overwhelmingly use plural names.
  if (snake.endsWith('y')) candidates.add(snake.slice(0, -1) + 'ies')
  if (snake.endsWith('s') || snake.endsWith('x') || snake.endsWith('ch') || snake.endsWith('sh')) {
    candidates.add(snake + 'es')
  } else {
    candidates.add(snake + 's')
  }
  return [...candidates]
}

function extractTableNames(dbTypesContent: string): Set<string> {
  // Pull table names from the generated Database['public']['Tables'] block.
  // Generated shape (4-space indent for Tables/Views, 6-space for table
  // names, 8-space for Row/Insert/Update):
  //   Tables: {
  //     table_name: {
  //       Row: { ... }
  //     }
  //   }
  //   Views: { ... }
  const lines = dbTypesContent.split('\n')
  const names = new Set<string>()
  let inTablesBlock = false
  for (const line of lines) {
    if (/^ {4}Tables:\s*\{/.test(line)) {
      inTablesBlock = true
      continue
    }
    if (inTablesBlock && /^ {4}Views:\s*\{/.test(line)) {
      inTablesBlock = false
      break
    }
    if (!inTablesBlock) continue
    // Six-space-indented table name with opening brace.
    const m = line.match(/^ {6}(\w+):\s*\{$/)
    if (m) names.add(m[1])
  }
  return names
}

function findFreestandingInterfaces(
  typesContent: string,
  tableNames: Set<string>,
): Array<{ interfaceName: string; tableName: string }> {
  const offenders: Array<{ interfaceName: string; tableName: string }> = []
  // Match `export interface Name [extends ...] {` and capture name + a
  // generous slice of declaration text (extends clause + body).
  const regex = /^export interface (\w+)([^{]*)\{([\s\S]*?)\n\}/gm
  let m: RegExpExecArray | null
  while ((m = regex.exec(typesContent)) !== null) {
    const name = m[1]
    if (EXEMPT_INTERFACES.has(name)) continue
    const decl = (m[2] || '') + (m[3] || '')

    for (const candidate of tableCandidates(name)) {
      if (!tableNames.has(candidate)) continue
      // Interface name matches a real table — must reference Tables<'name'>.
      if (!decl.includes(`Tables<'${candidate}'>`)) {
        offenders.push({ interfaceName: name, tableName: candidate })
      }
      break
    }
  }
  return offenders
}

describe('types.ts drift safeguard', () => {
  it('every table-shaped interface anchors to Tables<>', () => {
    // Normalize CRLF — generated file is committed with Windows line endings
    // on this checkout; regexes anchored with `$` get confused.
    const typesContent = readFileSync(join(__dirname, 'types.ts'), 'utf8').replace(/\r\n/g, '\n')
    const dbContent = readFileSync(join(__dirname, 'database.types.ts'), 'utf8').replace(/\r\n/g, '\n')
    const tableNames = extractTableNames(dbContent)
    expect(tableNames.size).toBeGreaterThan(0)

    const offenders = findFreestandingInterfaces(typesContent, tableNames)
    if (offenders.length > 0) {
      const lines = offenders.map(
        (o) => `  - interface ${o.interfaceName} mirrors table '${o.tableName}' but doesn't extend Tables<'${o.tableName}'>`,
      )
      throw new Error(
        `Found ${offenders.length} freestanding table-mirror interface(s):\n` +
          lines.join('\n') +
          `\n\nFix: refactor each to \`extends Omit<Tables<'tablename'>, ...> { ...narrowed columns... }\` ` +
          `so dropped/renamed columns become a compile error.\n` +
          `If the interface is intentionally freestanding (composite/view/DTO), add it to EXEMPT_INTERFACES with a reason.`,
      )
    }
  })
})
