/**
 * Execute the real subscriber migrations against disposable PostgreSQL WASM.
 * Pass an installed @electric-sql/pglite@0.5.8 module path. No network or env.
 * Broad defaults intentionally model hosted grants, including PUBLIC/TRUNCATE.
 */
import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { randomUUID } from 'node:crypto'

if (!process.argv[2]) throw new Error('Pass the path to an installed PGlite module')
const { PGlite } = await import(pathToFileURL(resolve(process.argv[2])).href)
const migrationUrl = name => new URL(`../src/migrations/${name}`, import.meta.url)
const tables = ['email_subscribers', 'email_preferences']
const privileges = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER']
let checks = 0
const verify = (actual, expected) => { assert.deepEqual(actual, expected); checks++ }

async function scenario(withSubjects) {
  const db = new PGlite()
  const migration = async name => db.exec(await readFile(migrationUrl(name), 'utf8'))
  const denied = async query => {
    await assert.rejects(() => db.query(query), error => error.code === '42501')
    checks++
  }
  const subscriberId = randomUUID()
  const preferenceId = randomUUID()
  const accessSnapshot = async () => (await db.query(`
    SELECT c.relname, a.privilege_type, a.is_grantable
    FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a
    WHERE c.oid IN ('public.email_subscribers'::regclass, 'public.email_preferences'::regclass)
      AND a.grantee = 'service_role'::regrole ORDER BY 1,2,3
  `)).rows
  const policySnapshot = async () => (await db.query(`
    SELECT tablename,policyname,roles,cmd,qual,with_check FROM pg_policies
    WHERE schemaname='public' AND tablename IN ('email_subscribers','email_preferences')
    ORDER BY 1,2
  `)).rows
  const functionSnapshot = async () => (await db.query(`
    SELECT p.oid::regprocedure::text signature,p.proacl::text acl,pg_get_functiondef(p.oid) definition
    FROM pg_proc p WHERE p.pronamespace='public'::regnamespace ORDER BY 1
  `)).rows
  try {
    // service_role has no BYPASSRLS: existing named policies must keep working.
    // public_only has no explicit grants and detects a missed PUBLIC revoke.
    await db.exec(`
      CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE public_only; CREATE ROLE service_role;
      GRANT USAGE ON SCHEMA public TO anon,authenticated,public_only,service_role;
      ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO PUBLIC,anon,authenticated,service_role;
      ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO anon,authenticated,service_role;
      CREATE TABLE meetings(id uuid PRIMARY KEY);
    `)
    await migration('079_email_subscribers.sql')
    await migration('080_email_preferences.sql')
    await db.query("INSERT INTO email_subscribers(id,email) VALUES($1,'fixture@example.test')", [subscriberId])
    await db.query("INSERT INTO email_preferences(id,subscriber_id,preference_type,preference_value) VALUES($1,$2,'topic','housing')", [preferenceId, subscriberId])

    // First reproduce why RLS alone is insufficient, entirely in a rollback.
    await db.exec('BEGIN; SET LOCAL ROLE anon;')
    verify((await db.query('SELECT * FROM email_subscribers')).rows, [])
    await db.exec('TRUNCATE email_subscribers, email_preferences; RESET ROLE;')
    verify((await db.query('SELECT count(*)::int n FROM email_subscribers')).rows[0].n, 0)
    await db.exec('ROLLBACK')
    verify((await db.query('SELECT count(*)::int n FROM email_subscribers')).rows[0].n, 1)

    for (const name of ['092_subscriber_last_orientation.sql', '141_email_deliveries.sql', '142_tighten_email_delivery_grants.sql']) await migration(name)
    if (withSubjects) {
      for (const name of ['016_pending_decisions.sql', '149_operator_review_inbox.sql', '150_subscription_subject_follows.sql']) await migration(name)
    }
    const serviceBefore = await accessSnapshot()
    const policiesBefore = await policySnapshot()
    const functionsBefore = await functionSnapshot()
    const subscribersBefore = (await db.query('SELECT * FROM email_subscribers ORDER BY id')).rows
    const preferencesBefore = (await db.query('SELECT * FROM email_preferences ORDER BY id')).rows
    await migration('151_restrict_subscriber_table_access.sql')
    await migration('151_restrict_subscriber_table_access.sql')
    verify(await accessSnapshot(), serviceBefore)
    verify(await policySnapshot(), policiesBefore)
    verify(await functionSnapshot(), functionsBefore)
    verify((await db.query('SELECT * FROM email_subscribers ORDER BY id')).rows, subscribersBefore)
    verify((await db.query('SELECT * FROM email_preferences ORDER BY id')).rows, preferencesBefore)
    verify((await db.query("SELECT relrowsecurity FROM pg_class WHERE oid IN ('email_subscribers'::regclass,'email_preferences'::regclass)")).rows, [{ relrowsecurity: true }, { relrowsecurity: true }])

    for (const role of ['anon', 'authenticated', 'public_only']) {
      for (const table of tables) {
        for (const privilege of privileges) {
          verify((await db.query('SELECT has_table_privilege($1,$2,$3) allowed', [role, `public.${table}`, privilege])).rows[0].allowed, false)
        }
      }
      await db.exec(`SET ROLE ${role}`)
      for (const table of tables) {
        await denied(`SELECT * FROM ${table}`)
        await denied(`UPDATE ${table} SET city_fips='9999999'`)
        await denied(`DELETE FROM ${table}`)
        await denied(`TRUNCATE ${table} CASCADE`)
      }
      await denied("INSERT INTO email_subscribers(email) VALUES('forbidden@example.test')")
      await denied(`INSERT INTO email_preferences(subscriber_id,preference_type,preference_value) VALUES('${subscriberId}','topic','forbidden')`)
      await denied(`SELECT replace_email_preferences('${subscriberId}')`)
      await denied(`SELECT * FROM claim_email_delivery('${subscriberId}','digest','week:2026-09-07','${'a'.repeat(64)}')`)
      if (withSubjects) {
        await denied("SELECT activate_email_subscription_v2('forbidden@example.test','Resident','subscribe_page','2026-general')")
        await denied(`SELECT replace_email_preferences_v2('${subscriberId}','${randomUUID()}','{}','{}','{}','{}',true)`)
      }
      await db.exec('RESET ROLE')
    }

    // Existing service-backed routes can still read tokens, update consent,
    // replace preferences transactionally, activate, and claim a welcome.
    await db.exec('SET ROLE service_role')
    verify((await db.query('SELECT id,unsubscribe_token FROM email_subscribers WHERE id=$1', [subscriberId])).rows.length, 1)
    verify((await db.query('SELECT id FROM email_preferences WHERE subscriber_id=$1', [subscriberId])).rows.length, 1)
    await db.query('SELECT replace_email_preferences($1,$2,$3,$4)', [subscriberId, ['budget'], ['3'], []])
    verify((await db.query('SELECT preference_value FROM email_preferences WHERE subscriber_id=$1 ORDER BY 1', [subscriberId])).rows, [{ preference_value: '3' }, { preference_value: 'budget' }])
    const created = randomUUID()
    const activation = randomUUID()
    await db.query(`INSERT INTO email_subscribers(id,email,current_activation_id,current_activation_at,current_activation_surface,subscribed_at)
      VALUES($1,'activation@example.test',$2,now(),'subscribe_page',now())`, [created, activation])
    verify((await db.query('SELECT count(*)::int n FROM subscription_activations WHERE subscriber_id=$1', [created])).rows[0].n, 1)
    const claim = (await db.query('SELECT * FROM claim_email_delivery($1,$2,$3,$4)', [created, 'welcome', `welcome:${activation}`, 'a'.repeat(64)])).rows[0]
    verify(claim.delivery_disposition, 'claimed')
    await db.query("UPDATE email_subscribers SET status='unsubscribed',unsubscribed_at=now() WHERE id=$1", [created])
    verify((await db.query('SELECT status FROM email_subscribers WHERE id=$1', [created])).rows[0].status, 'unsubscribed')
    const directPreference = randomUUID()
    await db.query("INSERT INTO email_preferences(id,subscriber_id,preference_type,preference_value) VALUES($1,$2,'topic','direct')", [directPreference, subscriberId])
    verify((await db.query("UPDATE email_preferences SET preference_value='changed' WHERE id=$1", [directPreference])).affectedRows, 1)
    verify((await db.query('DELETE FROM email_preferences WHERE id=$1', [directPreference])).affectedRows, 1)
    verify((await db.query('DELETE FROM email_subscribers WHERE id=$1', [created])).affectedRows, 1)
    if (withSubjects) {
      const follow = (await db.query("SELECT activate_email_subscription_v2('follow@example.test','Resident','subscribe_page','2026-general') result")).rows[0].result
      verify(follow.activated, true)
      await db.query('SELECT replace_email_preferences_v2($1,$2,$3,$4,$5,$6,$7)', [follow.subscriber_id, follow.unsubscribe_token, [], [], [], ['flock-cameras-and-data-privacy'], false])
      verify((await db.query('SELECT preference_value FROM email_preferences WHERE subscriber_id=$1', [follow.subscriber_id])).rows, [{ preference_value: 'flock-cameras-and-data-privacy' }])
    }
    await db.exec('RESET ROLE')
  } finally { await db.close() }
}

await scenario(false) // Applying before the new subject-follow frontend is safe.
if (existsSync(migrationUrl('150_subscription_subject_follows.sql'))) await scenario(true)
console.log(`Subscriber table access: ${checks} PostgreSQL assertions passed; replay, preserved rows/service/RPCs verified.`)
