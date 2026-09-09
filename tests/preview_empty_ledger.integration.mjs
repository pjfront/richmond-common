/** Real PostgreSQL checks of the controller's actual ledger SQL. No live services. */
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const { PGlite } = await import(pathToFileURL(resolve(process.argv[2])).href)
const queries = JSON.parse(execFileSync(process.env.PYTHON || 'python', ['-c',
  "import sys,json;sys.path.insert(0,'src');import supabase_preview as p;print(json.dumps({'shape':p._EMPTY_LEDGER_SHAPE_QUERY,'rows':p._EMPTY_LEDGER_ROWS_QUERY,'guard':p._empty_ledger_guard_sql(),'init':p._LEDGER_INIT_SQL}))"], { encoding: 'utf8' }))
const db = new PGlite()
let checks = 0
const shape = async () => (await db.query(queries.shape)).rows[0]?.compatible
const denied = async () => { await assert.rejects(db.exec(queries.guard), error => error.code === '55000'); checks++ }
try {
  await db.exec('CREATE ROLE ledger_other; CREATE SCHEMA supabase_migrations; CREATE TABLE public.sentinel(id int);')
  // No ledger remains a supported fresh-branch state.
  await db.exec(queries.guard); checks++
  // Exact CLI v2.112.0 history.go DDL, before any migration is applied.
  await db.exec(`CREATE TABLE supabase_migrations.schema_migrations(version text NOT NULL PRIMARY KEY);
    ALTER TABLE supabase_migrations.schema_migrations ADD COLUMN statements text[];
    ALTER TABLE supabase_migrations.schema_migrations ADD COLUMN name text;`)
  assert.equal(await shape(), true); checks++
  assert.deepEqual((await db.query(queries.rows)).rows, [{ has_rows: false }]); checks++
  await db.exec(`BEGIN; ${queries.guard} ROLLBACK;`); checks++
  // The existing full initializer is the second and only other accepted shape.
  await db.exec(queries.init)
  assert.equal(await shape(), true); checks++
  await db.exec(`BEGIN; ${queries.guard} ROLLBACK;`); checks++
  const mutations = [
    'ALTER TABLE supabase_migrations.schema_migrations ADD COLUMN unexpected text',
    'ALTER TABLE supabase_migrations.schema_migrations ADD COLUMN dropped text; ALTER TABLE supabase_migrations.schema_migrations DROP COLUMN dropped',
    "ALTER TABLE supabase_migrations.schema_migrations ALTER COLUMN name SET DEFAULT 'unreviewed'",
    'ALTER TABLE supabase_migrations.schema_migrations ALTER COLUMN name TYPE varchar',
    'ALTER TABLE supabase_migrations.schema_migrations ALTER COLUMN name SET NOT NULL',
    'ALTER TABLE supabase_migrations.schema_migrations OWNER TO ledger_other',
    'ALTER TABLE supabase_migrations.schema_migrations ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE supabase_migrations.schema_migrations ADD CONSTRAINT unknown_check CHECK(name IS NULL)',
    'ALTER TABLE supabase_migrations.schema_migrations DROP CONSTRAINT schema_migrations_pkey',
    'ALTER TABLE supabase_migrations.schema_migrations DROP CONSTRAINT schema_migrations_pkey; ALTER TABLE supabase_migrations.schema_migrations ADD PRIMARY KEY(version) DEFERRABLE',
    'CREATE INDEX unexpected_index ON supabase_migrations.schema_migrations(name)',
    `CREATE FUNCTION supabase_migrations.unreviewed_trigger() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RETURN NEW; END$$;
     CREATE TRIGGER unreviewed BEFORE INSERT ON supabase_migrations.schema_migrations FOR EACH ROW EXECUTE FUNCTION supabase_migrations.unreviewed_trigger()`,
    `CREATE RULE unreviewed AS ON DELETE TO supabase_migrations.schema_migrations DO INSTEAD NOTHING`,
  ]
  for (const mutation of mutations) {
    await db.exec('BEGIN')
    await db.exec(mutation)
    assert.equal(await shape(), false, mutation); checks++
    await denied()
    await db.exec('ROLLBACK')
  }
  // A row inserted after a successful preflight is rejected atomically before
  // destructive restore commands; history and the sentinel remain untouched.
  assert.equal(await shape(), true); checks++
  await db.exec("INSERT INTO supabase_migrations.schema_migrations(version,name) VALUES('20260906015200','must_not_adopt')")
  await db.exec('BEGIN')
  await assert.rejects(db.exec(`${queries.guard} DROP TABLE public.sentinel;`), error => error.code === '55000'); checks++
  await db.exec('ROLLBACK')
  assert.equal((await db.query('SELECT count(*)::int n FROM supabase_migrations.schema_migrations')).rows[0].n, 1); checks++
  assert.equal((await db.query("SELECT to_regclass('public.sentinel') IS NOT NULL AS present")).rows[0].present, true); checks++
  console.log(`${checks} PostgreSQL assertions passed: exact empty ledger shapes, nonstandard metadata denial, late history preservation and atomic restore guard`)
} finally { await db.close() }
