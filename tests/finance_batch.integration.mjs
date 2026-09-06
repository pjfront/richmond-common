/** Execute the batch writer's actual SQL with >2 batches and a replay. */
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { pathToFileURL, fileURLToPath } from 'node:url'

const { PGlite } = await import(pathToFileURL(resolve(process.argv[2])).href)
const fixture = JSON.parse(execFileSync(process.argv[3] || 'python',[fileURLToPath(new URL('./finance_batch_sql_fixture.py',import.meta.url))],{encoding:'utf8',maxBuffer:16*1024*1024}))
const db=new PGlite()
try {
  await db.exec(`CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role;
    CREATE TABLE documents(id uuid PRIMARY KEY,city_fips text,source_type text,source_url text,source_identifier text,
      raw_content bytea,content_hash text,mime_type text,credibility_tier integer,metadata jsonb,UNIQUE(city_fips,content_hash));`)
  await db.exec(await readFile(new URL('../src/migrations/148_finance_assertion_ledger.sql',import.meta.url),'utf8'))
  const run=async(phase,failCoverage=false)=>{
    for(const command of phase.commands){
      let index=0
      const query=command.sql.replace(/%s/g,()=>`$${++index}`)
      const params=command.parameters.map(value=>typeof value==='string' && /^\\x[0-9a-f]+$/.test(value)
        ? Uint8Array.from(Buffer.from(value.slice(2),'hex')) : value)
      if(failCoverage && query.startsWith('INSERT INTO "finance_source_coverage"')) {
        // Failure in the final batch must roll back documents, assertions and
        // projection selection, not just coverage.
        const columns=query.match(/\(([^)]+)\) VALUES/)[1].split(',').map(c=>c.replaceAll('"',''))
        params[columns.indexOf('confidence_score')]=null
      }
      await db.query(query,params)
    }
  }
  const count=async(table)=>Number((await db.query(`SELECT count(*) n FROM ${table}`)).rows[0].n)
  const sourceBytes=async()=> (await db.query(`SELECT record_key,content_hash,amount,raw_payload,is_current FROM finance_assertions ORDER BY record_key,content_hash`)).rows
  await db.exec('BEGIN');await run(fixture.phases[0]);await db.exec('COMMIT')
  assert.equal(await count('documents'),504)
  assert.equal(await count('finance_assertions'),503)
  assert.equal(await count('finance_public_events'),503)
  assert.equal(await count('finance_public_coverage'),7)
  const original=await sourceBytes()
  await db.exec('BEGIN');await run(fixture.phases[1]);await db.exec('COMMIT')
  assert.deepEqual(await sourceBytes(),original)
  assert.equal(await count('documents'),504)
  assert.equal(fixture.phases[1].stats.assertions_inserted,0)
  assert.equal(fixture.phases[1].stats.assertion_versions_updated,0)
  assert(!fixture.phases[1].commands.some(c=>c.sql.startsWith('INSERT INTO finance_assertions') || c.sql.startsWith('INSERT INTO documents')))
  await db.exec('BEGIN')
  await assert.rejects(run(fixture.phases[2],true),e=>e.code==='23502')
  await db.exec('ROLLBACK')
  assert.deepEqual(await sourceBytes(),original)
  assert.equal(await count('documents'),504)
  assert.equal(await count('finance_public_events'),503)
  await db.exec('BEGIN');await run(fixture.phases[2]);await db.exec('COMMIT')
  assert.equal(await count('finance_assertions'),504)
  assert.equal(await count('finance_public_events'),503)
  assert.equal((await db.query("SELECT amount,is_current FROM finance_assertions WHERE filing_id='100000'")).rows[0].amount,'30000.00')
  assert.equal((await db.query("SELECT is_current FROM finance_assertions WHERE filing_id='100000'")).rows[0].is_current,false)
  assert.equal((await db.query("SELECT amount,amends_filing_id FROM finance_assertions WHERE filing_id='200000'")).rows[0].amount,'25000.00')
  assert.equal(Number((await db.query(`SELECT count(*) n FROM finance_events e CROSS JOIN LATERAL unnest(e.assertion_ids) linked
    LEFT JOIN finance_assertions a ON a.id=linked WHERE a.id IS NULL`)).rows[0].n),0)
  assert.equal(Number((await db.query(`SELECT count(*) n FROM finance_assertions a LEFT JOIN documents d ON a.document_id=d.id WHERE d.id IS NULL`)).rows[0].n),0)
  assert(fixture.phases.every(p=>p.commands.filter(c=>c.batch_size).every(c=>c.batch_size<=250)))
  console.log(`Passed PostgreSQL batch writer proof: 503 assertions, 504 documents, unchanged replay, amendment lineage, valid references, complete rollback; roundtrips ${fixture.phases.map(p=>`${p.name}=${p.commands.length}`).join(', ')}.`)
}catch(error){console.error(error.message,error.code||'');process.exitCode=1}
finally{await db.close()}
