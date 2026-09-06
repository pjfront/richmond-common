/** Isolated real PostgreSQL execution via PGlite; never uses live credentials. */
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

if (!process.argv[2]) throw new Error('Pass the path to an installed PGlite module')
const { PGlite } = await import(pathToFileURL(resolve(process.argv[2])).href)
const db = new PGlite()
const migration = await readFile(new URL('../src/migrations/148_finance_assertion_ledger.sql', import.meta.url), 'utf8')
const mirror = await readFile(new URL('../supabase/migrations/20260906014800_finance_assertion_ledger.sql', import.meta.url), 'utf8')
assert.equal(migration, mirror)
let checks = 0
try {
  await db.exec(`CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role;
    GRANT USAGE ON SCHEMA public TO anon,authenticated,service_role;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO PUBLIC,anon,authenticated,service_role;
    CREATE TABLE documents(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),source_type text NOT NULL);
    ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
    CREATE POLICY public_read ON documents FOR SELECT USING(true);
    INSERT INTO documents(source_type) VALUES ('agenda'),('netfile_496'),('netfile_transaction');`)
  await db.exec(migration)
  await db.exec(migration)
  await db.exec('SET ROLE service_role')
  const insert = `INSERT INTO finance_assertions(source,scope_key,record_key,content_hash,filing_id,transaction_id,form_type,
    reporting_filer_name,event_kind,amount,amount_kind,activity_date,raw_payload,source_url,confidence_score)
    VALUES ('netfile','0660620:calendar-2026','216765092:one',repeat('a',64),'216765092','one','F497P2',
    'Richmond Police Officers Association PAC','transfer',30000,'monetary','2026-05-12','{"transactionType":21}',
    'https://netfile.com/Connect2/api/public/image/216765092',0.99)
    ON CONFLICT(source,record_key,content_hash) DO UPDATE SET is_current=EXCLUDED.is_current
    RETURNING id`
  const first = (await db.query(insert)).rows[0].id
  assert.equal((await db.query(insert)).rows[0].id, first); checks++
  await db.exec(`UPDATE finance_assertions SET is_current=false,reconciliation_status='pending_review',review_reason='fixture'`)
  await assert.rejects(db.query(`UPDATE finance_assertions SET amount=60000`), e => e.message.includes('immutable')); checks++
  await assert.rejects(db.query('DELETE FROM finance_assertions'), e => e.code === '42501'); checks++
  await assert.rejects(db.query('TRUNCATE finance_assertions'), e => e.code === '42501'); checks++
  await db.exec(`INSERT INTO finance_events(event_key,source,scope_key,event_kind,reporting_filer_name,amount,amount_kind,
    activity_date,filing_ids,source_urls,assertion_ids,reconciliation_status,source_url,extracted_at,source_tier,confidence_score)
    VALUES ('visible','netfile','0660620:calendar-2026','transfer','RPOA',30000,'monetary','2026-05-12',
    ARRAY['216765092'],ARRAY['https://netfile.com/Connect2/api/public/image/216765092'],ARRAY['${first}']::uuid[],
    'source_reported','https://netfile.com/Connect2/api/public/image/216765092',now(),1,0.99);
    INSERT INTO finance_events SELECT 'pending',source,scope_key,event_kind,reporting_filer_name,reporting_filer_fppc_id,
    donor_name,donor_fppc_id,recipient_name,recipient_fppc_id,amount,amount_kind,activity_date,support_oppose,candidate_name,
    measure_name,election_date,description,filing_ids,source_urls,assertion_ids,'pending_review',is_current,source_url,
    extracted_at,source_tier,confidence_score FROM finance_events WHERE event_key='visible';
    INSERT INTO finance_source_coverage(source,form_type,scope_key,status,checked_at,source_url,extracted_at,confidence_score)
    VALUES('netfile','F497P2','0660620:calendar-2026','partial',now(),'https://public.netfile.com/pub2/?AID=RICH',now(),1);`)
  await db.exec('RESET ROLE')
  await db.exec(migration) // replay preserves raw evidence and projections
  assert.equal((await db.query('SELECT amount FROM finance_assertions')).rows[0].amount, '30000.00'); checks++
  for (const role of ['anon','authenticated']) {
    await db.exec(`SET ROLE ${role}`)
    for (const table of ['finance_assertions','finance_events','finance_source_coverage']) {
      for (const statement of [`INSERT INTO ${table} DEFAULT VALUES`,`UPDATE ${table} SET source='bad'`,`DELETE FROM ${table}`,`TRUNCATE ${table}`]) {
        await assert.rejects(db.query(statement), e => e.code === '42501'); checks++
      }
    }
    await assert.rejects(db.query('SELECT * FROM finance_assertions'), e => e.code === '42501'); checks++
    for (const view of ['finance_public_events','finance_public_coverage']) {
      for (const operation of ['INSERT','UPDATE','DELETE','TRUNCATE']) {
        assert.equal((await db.query('SELECT has_table_privilege($1,$2,$3) allowed', [role,view,operation])).rows[0].allowed, false); checks++
      }
    }
    assert.deepEqual((await db.query('SELECT event_key FROM finance_public_events')).rows, [{event_key:'visible'}]); checks++
    assert.equal((await db.query('SELECT status FROM finance_public_coverage')).rows[0].status, 'partial'); checks++
    assert.deepEqual((await db.query('SELECT source_type FROM documents')).rows, [{source_type:'agenda'}]); checks++
    const columns = Object.keys((await db.query('SELECT * FROM finance_public_events')).rows[0])
    assert(!columns.some(c => ['raw_payload','line1','street_address','assertion_ids'].includes(c))); checks++
    await db.exec('RESET ROLE')
  }
  // Even an owner cannot mutate/delete source evidence. An amendment is a
  // new content version, so both amounts and the original raw record survive.
  await assert.rejects(db.query('DELETE FROM finance_assertions'), e => e.message.includes('cannot be deleted')); checks++
  await db.exec(insert.replace("repeat('a',64)", "repeat('b',64)").replace("30000,'monetary'", "25000,'monetary'"))
  assert.equal((await db.query('SELECT count(*) n FROM finance_assertions')).rows[0].n, 2); checks++
  console.log(`Passed ${checks} PostgreSQL finance access, replay, raw-evidence and projection assertions.`)
} finally {
  await db.close()
}
