/**
 * Execute the migration against an isolated PostgreSQL WASM database.
 * No external database, network connection, or production environment is used.
 *
 * npm install --prefix tmp/sql-verify --no-audit --no-fund @electric-sql/pglite@0.5.8
 * node tests/operator_table_security.integration.mjs tmp/sql-verify/node_modules/@electric-sql/pglite/dist/index.js
 */
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

if (!process.argv[2]) throw new Error('Pass the path to an installed PGlite module')
const { PGlite } = await import(pathToFileURL(resolve(process.argv[2])).href)
const db = new PGlite()
const privateTables = ['pending_decisions', 'pipeline_journal']
const tables = [...privateTables, 'neighborhood_councils']
const sql = await readFile(new URL('../src/migrations/147_restrict_operator_table_access.sql', import.meta.url), 'utf8')

try {
  // service_role deliberately does not bypass RLS in this fixture: its named
  // policy must work independently of Supabase's service-role bypass flag.
  await db.exec('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role; GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;')
  for (const table of tables) {
    const policy = table === 'neighborhood_councils' ? 'neighborhood_councils_service_write' : `${table}_service_all`
    await db.exec(`
      CREATE TABLE public.${table} (id integer PRIMARY KEY, value text NOT NULL);
      INSERT INTO public.${table} VALUES (1, 'preserve me');
      ALTER TABLE public.${table} ENABLE ROW LEVEL SECURITY;
      CREATE POLICY ${policy} ON public.${table} FOR ALL USING (true) WITH CHECK (true);
      GRANT ALL ON public.${table} TO PUBLIC, anon, authenticated, service_role;
    `)
  }
  await db.exec('CREATE POLICY neighborhood_councils_public_read ON public.neighborhood_councils FOR SELECT USING (true);')

  await db.exec(sql)
  await db.exec(sql) // A replay must preserve both data and the boundary.
  for (const table of tables) {
    const { rows } = await db.query(`SELECT * FROM public.${table}`)
    assert.deepEqual(rows, [{ id: 1, value: 'preserve me' }])
  }

  let assertions = 0
  for (const role of ['anon', 'authenticated']) {
    await db.exec(`SET ROLE ${role}`)
    for (const table of tables) {
      const mutations = [
        `INSERT INTO public.${table} VALUES (2, 'forbidden')`,
        `UPDATE public.${table} SET value='forbidden'`,
        `DELETE FROM public.${table}`,
        `TRUNCATE public.${table}`,
      ]
      for (const statement of [...mutations, ...(privateTables.includes(table) ? [`SELECT * FROM public.${table}`] : [])]) {
        await assert.rejects(db.query(statement), (error) => error.code === '42501')
        assertions++
      }
    }
    assert.deepEqual((await db.query('SELECT * FROM public.neighborhood_councils')).rows,
      [{ id: 1, value: 'preserve me' }])
    assertions++
    await db.exec('RESET ROLE')
  }

  // Defense in depth: even if a future grant accidentally reopens table
  // privileges, the scoped RLS policy must still hide private state.
  for (const table of privateTables) {
    await db.exec(`GRANT SELECT, INSERT, UPDATE, DELETE ON public.${table} TO anon; SET ROLE anon;`)
    assert.deepEqual((await db.query(`SELECT * FROM public.${table}`)).rows, [])
    assert.equal((await db.query(`UPDATE public.${table} SET value='forbidden'`)).affectedRows, 0)
    assert.equal((await db.query(`DELETE FROM public.${table}`)).affectedRows, 0)
    await assert.rejects(db.query(`INSERT INTO public.${table} VALUES (2, 'forbidden')`), (error) => error.code === '42501')
    assertions += 4
    await db.exec('RESET ROLE')
  }
  await db.exec(sql)

  await db.exec('SET ROLE service_role')
  for (const table of tables) {
    assert.equal((await db.query(`SELECT * FROM public.${table}`)).rows.length, 1)
    await db.query(`INSERT INTO public.${table} VALUES (2, 'service write')`)
    assert.equal((await db.query(`UPDATE public.${table} SET value='service update' WHERE id=2`)).affectedRows, 1)
    assert.equal((await db.query(`DELETE FROM public.${table} WHERE id=2`)).affectedRows, 1)
    assertions += 4
  }
  await db.exec('RESET ROLE')
  console.log(`Passed ${assertions} PostgreSQL access assertions; migration replay and row preservation verified.`)
} finally {
  await db.close()
}
