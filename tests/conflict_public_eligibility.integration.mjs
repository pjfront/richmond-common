/** Execute actual policy/RPC SQL against disposable PostgreSQL; no live credentials. */
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
const { PGlite } = await import(pathToFileURL(resolve(process.argv[2])).href)
const db = new PGlite()
const migration = await readFile(new URL('../src/migrations/152_public_conflict_eligibility.sql', import.meta.url), 'utf8')
assert.equal(migration, await readFile(new URL('../supabase/migrations/20260906015200_public_conflict_eligibility.sql', import.meta.url), 'utf8'))
const sourceMigration = await readFile(new URL('../src/migrations/133_source_reconciliation_tombstones.sql', import.meta.url), 'utf8')
const sourcePolicy = sourceMigration.split('ALTER TABLE conflict_flags ENABLE ROW LEVEL SECURITY;')[1].split('ALTER TABLE meeting_attendance')[0]
const parentPolicies = 'ALTER TABLE agenda_items ENABLE ROW LEVEL SECURITY;' + sourceMigration
  .split('ALTER TABLE agenda_items ENABLE ROW LEVEL SECURITY;')[1].split('DROP POLICY IF EXISTS "Public read" ON nextrequest_requests;')[0]
let checks = 0
const id = n => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
const snapshot = async table => (await db.query(`SELECT md5(COALESCE(string_agg(to_jsonb(t)::text,'' ORDER BY to_jsonb(t)::text),'')) hash FROM ${table} t`)).rows[0].hash
try {
  await db.exec(`CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;
    GRANT USAGE ON SCHEMA public TO anon,authenticated,service_role;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO PUBLIC,anon,authenticated,service_role;
    CREATE TABLE meetings(id uuid PRIMARY KEY,city_fips text,source_cancelled_at timestamptz);
    CREATE TABLE agenda_items(id uuid PRIMARY KEY,meeting_id uuid,agenda_source_retired_at timestamptz);
    CREATE TABLE conflict_flags(id uuid PRIMARY KEY,meeting_id uuid,agenda_item_id uuid,city_fips text,
      is_current boolean,confidence numeric,false_positive boolean,flag_type text,evidence jsonb);
    ALTER TABLE conflict_flags ENABLE ROW LEVEL SECURITY;
    CREATE TABLE finance_events(payload jsonb); INSERT INTO finance_events VALUES(' {"immutable":1177} ');
    CREATE TABLE email_subscribers(payload jsonb); INSERT INTO email_subscribers VALUES('{"private":"fixture"}');
    INSERT INTO meetings VALUES('${id(1)}','0660620',NULL),('${id(2)}','0660620',now());
    INSERT INTO agenda_items VALUES('${id(11)}','${id(1)}',NULL),('${id(12)}','${id(2)}',NULL),('${id(13)}','${id(1)}',now());`)
  await db.exec(sourcePolicy)
  await db.exec(parentPolicies)
  const flags = [
    [101,id(1),id(11),true,0.90,false], [102,id(1),id(11),true,0.70,null],
    [103,id(1),id(11),true,0.69,false], [104,id(1),id(11),false,0.99,false],
    [105,id(1),id(11),true,0.99,true], [106,id(2),id(12),true,0.99,false],
    [107,id(1),id(13),true,0.99,false], [108,null,null,true,0.90,false],
    [109,id(1),id(11),null,0.99,false], [110,id(1),id(11),true,null,false],
    // A valid/missing direct meeting cannot hide a cancelled agenda parent.
    [111,null,id(12),true,0.99,false], [112,id(1),id(12),true,0.99,false],
  ]
  for (const [n,meeting,item,current,confidence,falsePositive] of flags) {
    await db.query('INSERT INTO conflict_flags VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)',[id(n),meeting,item,'0660620',current,confidence,falsePositive,'campaign_contribution',[{original:'retained source'}]])
  }
  const before = await snapshot('conflict_flags')
  const protectedBefore = [await snapshot('finance_events'),await snapshot('email_subscribers')]
  const serviceAcl = (await db.query(`SELECT privilege_type FROM information_schema.role_table_grants WHERE table_name='conflict_flags' AND grantee='service_role' ORDER BY privilege_type`)).rows
  await db.exec(migration)
  await db.exec(migration)
  assert.equal(await snapshot('conflict_flags'),before); checks++
  assert.deepEqual([await snapshot('finance_events'),await snapshot('email_subscribers')],protectedBefore); checks++
  assert.deepEqual((await db.query(`SELECT privilege_type FROM information_schema.role_table_grants WHERE table_name='conflict_flags' AND grantee='service_role' ORDER BY privilege_type`)).rows,serviceAcl); checks++
  assert.equal((await db.query(`SELECT count(*)::int n FROM pg_policies WHERE tablename='conflict_flags' AND policyname='Public read'`)).rows[0].n,1); checks++
  for (const role of ['anon','authenticated']) {
    await db.exec(`SET ROLE ${role}`)
    assert.deepEqual((await db.query('SELECT id FROM conflict_flags ORDER BY id')).rows.map(r=>r.id),[id(101),id(102),id(108)]); checks++
    assert.deepEqual((await db.query(`SELECT * FROM get_meeting_flag_counts('0660620') WHERE meeting_id=$1`,[id(1)])).rows,
      [{meeting_id:id(1),flags_total:2,flags_published:2,items_scanned:1}]); checks++
    assert.deepEqual((await db.query(`SELECT * FROM get_meeting_flag_counts('0660620') WHERE meeting_id=$1`,[id(2)])).rows,[]); checks++
    for (const privilege of ['INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER']) {
      assert.equal((await db.query('SELECT has_table_privilege($1,$2,$3) allowed',[role,'conflict_flags',privilege])).rows[0].allowed,false); checks++
    }
    for (const query of ['INSERT INTO conflict_flags DEFAULT VALUES',"UPDATE conflict_flags SET confidence=1",'DELETE FROM conflict_flags','TRUNCATE conflict_flags']) {
      await assert.rejects(db.query(query),e=>e.code==='42501'); checks++
    }
    await db.exec('RESET ROLE')
  }
  // PostgreSQL PUBLIC grants must not reintroduce dangerous privileges by inheritance.
  const publicWrites = (await db.query(`SELECT count(*)::int n FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a WHERE c.oid='conflict_flags'::regclass AND a.grantee=0 AND a.privilege_type<>'SELECT'`)).rows[0].n
  assert.equal(publicWrites,0); checks++
  await db.exec('SET ROLE service_role')
  assert.equal((await db.query('SELECT count(*)::int n FROM conflict_flags')).rows[0].n,12); checks++
  await db.exec(`BEGIN; UPDATE conflict_flags SET confidence=0.98 WHERE id='${id(103)}'; INSERT INTO conflict_flags(id) VALUES('${id(999)}'); DELETE FROM conflict_flags WHERE id='${id(999)}'; ROLLBACK;`); checks++
  await db.exec('RESET ROLE')
  assert.equal(await snapshot('conflict_flags'),before); checks++
  assert.deepEqual([await snapshot('finance_events'),await snapshot('email_subscribers')],protectedBefore); checks++
  const fn=(await db.query(`SELECT prosecdef,proconfig FROM pg_proc WHERE oid='get_meeting_flag_counts(text)'::regprocedure`)).rows[0]
  assert.equal(fn.prosecdef,true); checks++
  assert.deepEqual(fn.proconfig,['search_path=pg_catalog, pg_temp']); checks++
  console.log(`${checks} PostgreSQL assertions passed: public eligibility, source validity, all write privileges, RPC consistency, service access, immutable replay/protected rows`)
} finally { await db.close() }
