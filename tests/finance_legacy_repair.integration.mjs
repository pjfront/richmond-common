/** Replay the Python repair's actual statements against isolated PostgreSQL. */
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { pathToFileURL, fileURLToPath } from 'node:url'

if (!process.argv[2]) throw new Error('Pass the installed PGlite module path')
const { PGlite } = await import(pathToFileURL(resolve(process.argv[2])).href)
const fixture = JSON.parse(execFileSync(process.argv[3] || 'python', [fileURLToPath(new URL('./finance_legacy_repair_sql_fixture.py', import.meta.url))], {encoding:'utf8'}))
const migration = await readFile(new URL('../src/migrations/148_finance_assertion_ledger.sql', import.meta.url), 'utf8')
const db = new PGlite()
try {
  await db.exec(`CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role;
    CREATE TABLE documents(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),source_type text);
    CREATE TABLE donors(id text PRIMARY KEY,city_fips text,name text,normalized_name text,employer text);
    CREATE TABLE committees(id text PRIMARY KEY,name text,filer_id text);
    CREATE TABLE contributions(id text PRIMARY KEY,city_fips text,donor_id text REFERENCES donors(id),
      committee_id text REFERENCES committees(id),amount numeric(16,2),contribution_date date,
      contribution_type text,filing_id text,schedule text,source text,document_id uuid REFERENCES documents(id));
    INSERT INTO donors(id,name,normalized_name) VALUES('fixture-donor','Fixture','fixture'),('restore-donor','PAC 951606','pac 951606');`)
  await db.exec(migration)
  for (const committee of fixture.state.committees) {
    await db.query('INSERT INTO committees VALUES($1,$2,$3)', [committee.id,committee.name,committee.filer_id])
  }
  for (const entry of fixture.state.legacy) {
    const row = entry.before_row
    await db.query(`INSERT INTO contributions(id,donor_id,committee_id,amount,contribution_date,filing_id)
      VALUES($1,'fixture-donor',$2,$3,$4,$5)`, [row.id,row.committee_id,row.amount,row.contribution_date,row.filing_id])
  }
  const initialRows = (await db.query('SELECT * FROM contributions ORDER BY id')).rows
  const execute = async (failFinalInsert) => {
    for (const statement of fixture.statements) {
      let index = 0
      const sql = statement.sql.replace(/%s/g, () => `$${++index}`)
      const parameters = [...statement.parameters]
      if (failFinalInsert && sql.includes('INSERT INTO contributions')) parameters[1] = 'missing-donor-fk'
      await db.query(sql, parameters)
    }
  }
  await db.exec('BEGIN')
  await assert.rejects(execute(true), e => e.code === '23503')
  await db.exec('ROLLBACK')
  assert.deepEqual((await db.query('SELECT * FROM contributions ORDER BY id')).rows, initialRows)
  assert.equal((await db.query('SELECT count(*) n FROM finance_assertions')).rows[0].n, 0)
  assert.equal((await db.query("SELECT filer_id FROM committees WHERE id='1490887'")).rows[0].filer_id, 'Pending')

  await db.exec('BEGIN')
  await execute(false)
  await db.exec('COMMIT')
  assert.deepEqual(fixture.stats, {reversed_projections_removed:11,missing_receipts_restored:1,committee_ids_verified:1})
  assert.equal((await db.query('SELECT count(*) n FROM finance_assertions')).rows[0].n, 12)
  assert.equal((await db.query("SELECT count(*) n FROM finance_assertions WHERE raw_payload->'before' IS NOT NULL")).rows[0].n, 12)
  assert.equal((await db.query('SELECT count(*) n FROM contributions')).rows[0].n, 3)
  assert.equal((await db.query('SELECT sum(amount) total FROM contributions')).rows[0].total, '90000.00')
  assert.equal((await db.query("SELECT filer_id FROM committees WHERE id='1490887'")).rows[0].filer_id, '1490887')
  assert.deepEqual((await db.query("SELECT contribution_date::text FROM contributions WHERE contribution_date='2026-05-18'")).rows,
    [{contribution_date:'2026-05-18'}])
  console.log('Passed guarded repair PostgreSQL replay: 11 exact removals, 1 restoration, immutable backups, identity update and complete rollback on final-insert failure.')
} finally {
  await db.close()
}
