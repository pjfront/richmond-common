/** Disposable PostgreSQL only. Pass the installed PGlite 0.5.8 module path. */
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { randomUUID } from 'node:crypto'
const { PGlite } = await import(pathToFileURL(resolve(process.argv[2])).href)
const db = new PGlite()
let checks = 0
const verify = (actual, expected) => { assert.deepEqual(actual, expected); checks++ }
async function migration(name) { await db.exec(await readFile(new URL(`../src/migrations/${name}`, import.meta.url), 'utf8')) }
async function activate(email, subject = null) { return (await db.query('SELECT activate_email_subscription_v2($1,$2,$3,$4) result', [email, 'Resident', 'subscribe_page', subject])).rows[0].result }
async function preferences(id) { return (await db.query('SELECT preference_type,preference_value FROM email_preferences WHERE subscriber_id=$1 ORDER BY 1,2', [id])).rows }
async function replace(id, token, topics, subjects, council) { await db.query('SELECT replace_email_preferences_v2($1,$2,$3,$4,$5,$6,$7)', [id, token, topics, [], [], subjects, council]) }
async function claim(id, kind, key, refs = [], hash = 'a'.repeat(64)) { return (await db.query('SELECT * FROM claim_consented_email_delivery($1,$2,$3,$4,$5,$6)', [id, kind, key, hash, JSON.stringify(refs), kind !== 'digest' || !refs.length])).rows[0] }
async function denied(fn, code = '42501') { await assert.rejects(fn, error => error.code === code); checks++ }

try {
  await db.exec('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role; GRANT USAGE ON SCHEMA public TO anon,authenticated,service_role; CREATE TABLE meetings(id uuid PRIMARY KEY);')
  for (const name of ['079_email_subscribers.sql', '080_email_preferences.sql', '092_subscriber_last_orientation.sql', '141_email_deliveries.sql', '142_tighten_email_delivery_grants.sql', '016_pending_decisions.sql', '149_operator_review_inbox.sql']) await migration(name)
  await db.exec('GRANT SELECT,INSERT,UPDATE ON email_subscribers TO service_role; GRANT SELECT ON email_preferences TO service_role;')
  const legacyId = randomUUID()
  await db.query("INSERT INTO email_subscribers(id,email) VALUES($1,'legacy@example.test')", [legacyId])
  await migration('150_subscription_subject_follows.sql')
  await migration('150_subscription_subject_follows.sql')
  await db.query("INSERT INTO email_subscribers(email,city_fips,status) VALUES('other-city@example.test','9999999','unsubscribed')")
  verify((await db.query('SELECT receive_council_updates,current_activation_id FROM email_subscribers WHERE id=$1', [legacyId])).rows[0], { receive_council_updates: true, current_activation_id: null })
  for (const role of ['anon', 'authenticated']) {
    await db.exec(`SET ROLE ${role}`)
    await denied(() => activate('forbidden@example.test', '2026-general'))
    await denied(() => db.query('SELECT replace_email_preferences($1)', [legacyId]))
    await denied(() => replace(legacyId, randomUUID(), [], [], true))
    await denied(() => claim(legacyId, 'digest', 'week:2026-08-31'))
    await denied(() => db.query('SELECT * FROM email_preferences'))
    await db.exec('RESET ROLE')
  }
  await db.exec('SET ROLE service_role')
  verify(await activate('other-city@example.test', '2026-general'), { activated: false })
  const general = await activate('general@example.test')
  verify(general.receive_council_updates, true)
  await replace(general.subscriber_id, general.unsubscribe_token, ['housing'], ['2026-general'], true)
  await db.query("UPDATE email_subscribers SET status='unsubscribed' WHERE id=$1", [general.subscriber_id])
  const generalReactivated = await activate('general@example.test')
  verify(generalReactivated.receive_council_updates, true)
  verify(await preferences(general.subscriber_id), [{ preference_type: 'subject', preference_value: '2026-general' }, { preference_type: 'topic', preference_value: 'housing' }])
  const initial = await activate(' Follow@Example.Test ', '2026-general')
  verify(initial.activated, true)
  verify(initial.receive_council_updates, false)
  verify(await preferences(initial.subscriber_id), [{ preference_type: 'subject', preference_value: '2026-general' }])
  verify((await db.query('SELECT count(*)::int n FROM subscription_activations WHERE subscriber_id=$1', [initial.subscriber_id])).rows[0].n, 1)
  verify((await db.query('SELECT status,payload_sha256 FROM email_deliveries WHERE subscriber_id=$1', [initial.subscriber_id])).rows, [{ status: 'pending', payload_sha256: null }])
  verify(await activate('follow@example.test', 'flock-cameras-and-data-privacy'), { activated: false })
  verify(await preferences(initial.subscriber_id), [{ preference_type: 'subject', preference_value: '2026-general' }])
  await replace(initial.subscriber_id, initial.unsubscribe_token, ['chevron'], ['2026-general'], false)
  await denied(() => replace(initial.subscriber_id, initial.unsubscribe_token, ['new-topic'], ['invented-subject'], true), '23514')
  verify(await preferences(initial.subscriber_id), [{ preference_type: 'subject', preference_value: '2026-general' }, { preference_type: 'topic', preference_value: 'chevron' }])
  await db.query('SELECT replace_email_preferences($1,$2,$3,$4)', [initial.subscriber_id, ['housing_development'], [], []])
  verify(await preferences(initial.subscriber_id), [{ preference_type: 'subject', preference_value: '2026-general' }, { preference_type: 'topic', preference_value: 'housing_development' }])
  await denied(() => claim(initial.subscriber_id, 'orientation', `meeting:${randomUUID()}`))
  await denied(() => claim(initial.subscriber_id, 'recap', `meeting:${randomUUID()}`))
  await denied(() => claim(initial.subscriber_id, 'digest', 'week:2026-08-31'))
  await denied(() => db.query('SELECT * FROM claim_email_delivery($1,$2,$3,$4)', [initial.subscriber_id, 'orientation', `meeting:${randomUUID()}`, 'a'.repeat(64)]))
  await denied(() => db.query('SELECT * FROM claim_email_delivery_v141($1,$2,$3,$4)', [initial.subscriber_id, 'orientation', `meeting:${randomUUID()}`, 'a'.repeat(64)]))
  verify((await claim(initial.subscriber_id, 'welcome', `welcome:${initial.activation_id}`)).delivery_disposition, 'claimed')
  await db.query("UPDATE email_subscribers SET status='unsubscribed' WHERE id=$1", [initial.subscriber_id])
  await denied(() => replace(initial.subscriber_id, initial.unsubscribe_token, [], [], true))
  await denied(() => db.query('SELECT replace_email_preferences($1)', [initial.subscriber_id]))
  const reactivated = await activate('follow@example.test', 'fire-stations-and-emergency-response')
  verify(reactivated.subscriber_id, initial.subscriber_id)
  verify(reactivated.unsubscribe_token !== initial.unsubscribe_token, true)
  verify(reactivated.activation_id !== initial.activation_id, true)
  verify(reactivated.receive_council_updates, false)
  verify(await preferences(initial.subscriber_id), [{ preference_type: 'subject', preference_value: 'fire-stations-and-emergency-response' }])
  await denied(() => replace(initial.subscriber_id, initial.unsubscribe_token, [], [], true))
  await replace(initial.subscriber_id, reactivated.unsubscribe_token, [], ['2026-general'], false)
  await db.exec('RESET ROLE')

  // A failure after activation cannot leave a live subscription, rotated token,
  // orphaned activation, or pending welcome without its subject preference.
  await db.exec(`CREATE FUNCTION reject_test_preference() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'forced insertion failure'; END $$;
    CREATE TRIGGER reject_test_preference BEFORE INSERT ON email_preferences FOR EACH ROW EXECUTE FUNCTION reject_test_preference();`)
  await assert.rejects(() => activate('rollback@example.test', '2026-general')); checks++
  verify((await db.query("SELECT count(*)::int n FROM email_subscribers WHERE email='rollback@example.test'")).rows[0].n, 0)
  await db.exec('DROP TRIGGER reject_test_preference ON email_preferences; DROP FUNCTION reject_test_preference();')

  const briefId = randomUUID()
  await db.query(`INSERT INTO civic_brief_candidates(id,kind,subject_key,title,body,sources,input_fingerprint,status,published_at)
    VALUES($1,'story_update','2026-general','Reviewed update','An exact source-backed explanation.',
    '[{"url":"https://www.richmondca.gov/Archive.aspx?ADID=17785","title":"Official resolution","source_tier":1}]','fixture','published','2026-09-01T12:00:00Z')`, [briefId])
  const ref = { id: briefId, content_version: 1, published_at: '2026-09-01T12:00:00Z' }
  await db.exec('SET ROLE service_role')
  await denied(() => db.query('SELECT * FROM claim_consented_email_delivery($1,$2,$3,$4,$5,$6)', [initial.subscriber_id, 'digest', 'week:2026-08-31', 'a'.repeat(64), JSON.stringify([ref]), true]))
  const digest = await claim(initial.subscriber_id, 'digest', 'week:2026-08-31', [ref])
  verify(digest.delivery_disposition, 'claimed')
  await db.query('SELECT fail_email_delivery($1,$2,$3,$4)', [digest.delivery_id, digest.delivery_claim_token, 'test rejection', false])
  await db.exec('RESET ROLE')
  await db.query("UPDATE email_deliveries SET next_attempt_at=now()-interval '1 minute' WHERE id=$1", [digest.delivery_id])
  await db.query("UPDATE civic_brief_candidates SET status='draft',published_at=NULL WHERE id=$1", [briefId])
  await db.exec('SET ROLE service_role')
  await denied(() => claim(initial.subscriber_id, 'digest', 'week:2026-08-31', [ref]))
  await db.exec('RESET ROLE')
  // Republishing unchanged text is still a new publication event. Reject the
  // earlier publication reference independently of content_version changes.
  await db.query("UPDATE civic_brief_candidates SET status='published',published_at='2026-09-02T11:00:00Z' WHERE id=$1", [briefId])
  verify((await db.query('SELECT content_version FROM civic_brief_candidates WHERE id=$1', [briefId])).rows[0].content_version, 1)
  await db.exec('SET ROLE service_role')
  await denied(() => claim(initial.subscriber_id, 'digest', 'week:2026-08-31', [ref]))
  await db.exec('RESET ROLE')
  await db.query("UPDATE civic_brief_candidates SET status='draft',published_at=NULL WHERE id=$1", [briefId])
  await db.query("UPDATE civic_brief_candidates SET body='Revised source-backed explanation.' WHERE id=$1", [briefId])
  await db.query("UPDATE civic_brief_candidates SET status='published',published_at='2026-09-02T12:00:00Z' WHERE id=$1", [briefId])
  await db.exec('SET ROLE service_role')
  await denied(() => claim(initial.subscriber_id, 'digest', 'week:2026-08-31', [ref]))
  const updatedRef = { ...ref, content_version: 2, published_at: '2026-09-02T12:00:00Z' }
  verify((await claim(initial.subscriber_id, 'digest', 'week:2026-08-31', [updatedRef], 'b'.repeat(64))).delivery_disposition, 'manual_review')
  await replace(initial.subscriber_id, reactivated.unsubscribe_token, [], [], false)
  await denied(() => claim(initial.subscriber_id, 'digest', 'week:2026-08-31', [updatedRef]))
  await db.exec('RESET ROLE')
  console.log(`Subscription subjects: ${checks} database assertions passed; no external database or provider used.`)
} finally { await db.close() }
