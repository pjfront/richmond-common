/**
 * Disposable PostgreSQL execution; never connects to an external database.
 * npm install --prefix tmp/sql-verify --no-audit --no-fund @electric-sql/pglite@0.5.8
 * node tests/operator_review_inbox.integration.mjs tmp/sql-verify/node_modules/@electric-sql/pglite/dist/index.js
 */
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { randomUUID } from 'node:crypto'

if (!process.argv[2]) throw new Error('Pass the path to an installed PGlite module')
const { PGlite } = await import(pathToFileURL(resolve(process.argv[2])).href)
const db = new PGlite()
let checks = 0
const verify = (actual, expected) => { assert.deepEqual(actual, expected); checks++ }
async function migration(name) { await db.exec(await readFile(new URL(`../src/migrations/${name}`, import.meta.url), 'utf8')) }
async function row(table, id) { return (await db.query(`SELECT * FROM public.${table} WHERE id=$1`, [id])).rows[0] }
async function review(id, action, version, key = randomUUID(), note = null) {
  const response = await db.query('SELECT public.review_decision($1,$2,$3,$4,$5,$6) AS result', [id, action, version, key, note, 'operator'])
  return response.rows[0].result
}
async function decision(extra = {}) {
  const id = randomUUID()
  await db.query(`INSERT INTO public.pending_decisions
    (id,city_fips,decision_type,severity,title,description,source,evidence,review_class,action_kind,target_brief_id,target_content_version)
    VALUES ($1,'0660620','general','medium','Review a record','A prepared decision','test',$2::jsonb,$3,$4,$5,$6)`,
  [id, JSON.stringify(extra.evidence ?? {}), extra.review_class ?? 'engineering', extra.action_kind ?? 'resolve_only', extra.target_brief_id ?? null, extra.target_content_version ?? null])
  return id
}
async function publication(overrides = {}) {
  const id = randomUUID()
  const sources = overrides.sources ?? [{ url: 'https://www.ci.richmond.ca.us/Archive.aspx?ADID=1', title: 'Official minutes', source_tier: 1, source_date: '2026-07-07' }]
  await db.query(`INSERT INTO public.civic_brief_candidates(id,kind,subject_key,title,body,sources,input_fingerprint)
    VALUES ($1,'meeting_brief','meeting:2026-07-07','Meeting brief',$2,$3::jsonb,'sha256:fixture')`, [id, overrides.body ?? 'A source-backed plain text statement.', JSON.stringify(sources)])
  return { id, decision: await decision({ review_class: 'editorial', action_kind: 'publish_brief', target_brief_id: id, target_content_version: 1 }) }
}

try {
  await db.exec('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role; GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;')
  await migration('016_pending_decisions.sql')
  await db.exec('CREATE TABLE public.pipeline_journal(id uuid PRIMARY KEY); CREATE TABLE public.neighborhood_councils(id uuid PRIMARY KEY); CREATE POLICY neighborhood_councils_public_read ON public.neighborhood_councils FOR SELECT USING(true);')
  await migration('147_restrict_operator_table_access.sql')
  await migration('149_operator_review_inbox.sql')
  await migration('149_operator_review_inbox.sql')

  const generic = await decision({ evidence: { action: 'DROP TABLE meetings', execute_sql: 'untrusted text' } })
  const genericKey = randomUUID()
  verify((await review(generic, 'approve', 1, genericKey)).effect, 'decision_recorded')
  verify((await review(generic, 'approve', 1, genericKey)).replayed, true)
  verify((await db.query('SELECT count(*)::int AS n FROM operator_decision_events WHERE decision_id=$1', [generic])).rows[0].n, 1)
  verify((await review(generic, 'reject', 1, genericKey)).code, 'idempotency_conflict')
  verify((await review(generic, 'reject', 1)).code, 'stale_decision')
  const oldResolvedAt = (await row('pending_decisions', generic)).resolved_at
  verify((await review(generic, 'edit_note', 2, randomUUID(), 'Clarification')).ok, true)
  verify((await row('pending_decisions', generic)).resolved_at, oldResolvedAt)
  verify((await review(generic, 'reopen', 3)).status, 'pending')
  verify((await review(generic, 'defer', 4)).status, 'deferred')
  verify((await review(generic, 'approve', 5)).status, 'approved')

  // Competing clients both submit the version they saw. At most one wins.
  const competition = await decision()
  const competing = await Promise.all([review(competition, 'approve', 1), review(competition, 'reject', 1)])
  verify(competing.filter(result => result.ok).length, 1)
  verify(competing.filter(result => result.code === 'stale_decision').length, 1)

  const valid = await publication()
  await db.exec('SET ROLE anon')
  verify((await db.query('SELECT * FROM civic_brief_candidates')).rows.length, 0)
  await assert.rejects(review(valid.decision, 'approve', 1), error => error.code === '42501'); checks++
  await assert.rejects(db.query('SELECT * FROM operator_decision_events'), error => error.code === '42501'); checks++
  await db.exec('RESET ROLE; SET ROLE service_role')
  await assert.rejects(db.query("UPDATE civic_brief_candidates SET status='published' WHERE id=$1", [valid.id]), error => error.code === '42501'); checks++
  await assert.rejects(db.query('DELETE FROM civic_brief_candidates WHERE id=$1', [valid.id]), error => error.code === '42501'); checks++
  const approved = await review(valid.decision, 'approve', 1)
  verify(approved.effect, 'brief_published')
  await assert.rejects(db.query("DELETE FROM operator_decision_events"), error => error.code === '42501'); checks++
  await assert.rejects(db.query("UPDATE operator_decision_events SET actor='spoof'"), error => error.code === '42501'); checks++
  await assert.rejects(db.query("UPDATE civic_brief_candidates SET body='unreviewed edit' WHERE id=$1", [valid.id]), error => error.code === '23514'); checks++
  await db.exec('RESET ROLE; SET ROLE authenticated')
  verify((await db.query('SELECT id FROM civic_brief_candidates')).rows, [{ id: valid.id }])
  await assert.rejects(db.query("UPDATE civic_brief_candidates SET body='untrusted'"), error => error.code === '42501'); checks++
  await assert.rejects(review(valid.decision, 'withdraw', 2, randomUUID(), 'Untrusted'), error => error.code === '42501'); checks++
  await db.exec('RESET ROLE')
  verify((await review(valid.decision, 'reopen', 2)).code, 'withdraw_required')
  verify((await review(valid.decision, 'withdraw', 2)).code, 'withdraw_requires_published_brief_and_note')
  verify((await review(valid.decision, 'withdraw', 2, randomUUID(), 'A source needs correction.')).effect, 'brief_withdrawn')
  verify((await row('civic_brief_candidates', valid.id)).status, 'draft')
  const event = (await db.query("SELECT before_state,after_state FROM operator_decision_events WHERE decision_id=$1 AND action='withdraw'", [valid.decision])).rows[0]
  verify(event.before_state.brief.status, 'published')
  verify(event.after_state.brief.status, 'draft')
  verify(event.before_state.brief.body, event.after_state.brief.body)

  const stale = await publication()
  await db.query("UPDATE civic_brief_candidates SET body='Corrected draft' WHERE id=$1", [stale.id])
  verify((await row('civic_brief_candidates', stale.id)).content_version, 2)
  verify((await review(stale.decision, 'approve', 1)).code, 'stale_content')
  verify((await row('pending_decisions', stale.decision)).status, 'pending')
  verify((await row('civic_brief_candidates', stale.id)).status, 'draft')
  verify((await review(stale.decision, 'edit_note', 1, randomUUID(), 'Please refresh the packet.')).ok, true)

  for (const sources of [[], [{ url: 'javascript:alert(1)', title: 'Bad source', source_tier: 1 }], [{ url: 'http://127.0.0.1?x=a', title: 'Private host', source_tier: 1 }], [{ url: 'https://example.org', title: 'Stakeholder', source_tier: 3 }]]) {
    const invalid = await publication({ sources })
    verify((await review(invalid.decision, 'approve', 1)).ok, false)
    verify((await row('pending_decisions', invalid.decision)).review_version, 1)
    verify((await row('civic_brief_candidates', invalid.id)).status, 'draft')
  }
  for (const body of ['', '<b>Raw HTML</b>']) {
    const invalid = await publication({ body })
    verify((await review(invalid.decision, 'approve', 1)).code, 'invalid_publication')
  }
  await assert.rejects(review(generic, 'execute_sql', 6), error => error.code === '22023'); checks++

  // If a later write fails, publication and decision changes both roll back.
  const atomic = await publication()
  await db.exec("CREATE FUNCTION reject_test_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected audit failure'; END $$; CREATE TRIGGER test_reject_audit BEFORE INSERT ON operator_decision_events FOR EACH ROW EXECUTE FUNCTION reject_test_audit();")
  await assert.rejects(review(atomic.decision, 'approve', 1)); checks++
  verify((await row('pending_decisions', atomic.decision)).status, 'pending')
  verify((await row('civic_brief_candidates', atomic.id)).status, 'draft')
  await db.exec('DROP TRIGGER test_reject_audit ON operator_decision_events;')
  console.log(`Passed ${checks} PostgreSQL review/publication assertions, including stale competing requests and atomic rollback.`)
} finally { await db.close() }
