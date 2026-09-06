# Operator review inbox

The operator opens `/operator/decisions`, reads the exact proposed text and its sources, and chooses an action. Engineering and editorial decisions are separated. Notes, evidence, and before/after states remain in a private audit history.

`resolve_only` entries change decision status only. Approving a generic failure report does not run its suggested command or repair. `publish_brief` entries point to one `civic_brief_candidates` row and its `content_version`. Approval publishes that exact version only after source validation. No command, SQL, callback, or arbitrary action in evidence is executed.

## Producer contract

After migration 149, insert a draft into `civic_brief_candidates` with `kind` (`story_update`, `meeting_brief`, or `finance_brief`), `subject_key`, `title`, `body`, `sources`, and `input_fingerprint`. Sources are an array of objects containing `url`, `title`, `source_tier`, and `source_date` (use null when unavailable). Body content is plain Markdown without raw HTML. Service callers must omit status/version/publication-attribution fields: the database supplies defaults, and only the review RPC can change publication state.

Create the decision through `decision_queue.create_decision()` using `review_class="editorial"`, `action_kind="publish_brief"`, `target_brief_id=brief_id`, and `target_content_version` equal to the actual returned candidate version. Supply an evidence object with `recommendation`, `alternatives`, `affected_pages`, and linked source excerpts. These fields are presented as readable blocks in the inbox. The normal title, description, severity, and source fields remain required.

Content/source/fingerprint edits increment content_version automatically. Review edits increment review_version. A stale packet cannot publish; refresh its target version only after the new text and evidence are ready for review. Published text cannot change in place. Prepare a new candidate, or explicitly withdraw with an explanation before editing. Withdrawal returns the brief to draft and reopens its decision; the audit preserves the former public text.

## Actions and guarantees

POST `/api/operator/decisions` requires the operator cookie, matching Origin, same-origin fetch metadata when present, and JSON. Its only accepted fields are `decision_id`, `action`, `expected_version`, `idempotency_key`, and `note`. Actions are approve, reject, defer, reopen, edit_note, and withdraw.

The service-only review_decision RPC locks the decision and target, checks both versions, validates publication sources, applies the allowed transition, and records operator_decision_events in one transaction. A matching retry key returns the original result. Reusing it for different input fails. If audit insertion fails, publication and decision changes roll back. Defer remains visible and deduplicated in the open inbox. Ordinary reopen never unpublishes content; withdraw is explicit and requires a note.

Publication requires nonempty title/body/fingerprint and named HTTP(S) sources at official-record or independent-journalism tiers (1 or 2). Local/private literal hosts, unsafe schemes, empty sources, stakeholder-only sources, and raw HTML are rejected. This validates the publication contract; it does not independently fact-check source content or the producer's tier assignment. The operator reviews those assertions in the packet.

## Integration and validation

Apply migration 149 before serving the updated inbox; migration 147 is its security prerequisite. No generated row types were hand-edited. Regenerate `web/src/lib/database.types.ts` from the migrated isolated schema during integration; inbox types use explicit API projections anchored to the existing generated decision row.

Run npm test and npx tsc --noEmit in web, plus the focused Python review tests. The executable PostgreSQL verifier is documented at the top of tests/operator_review_inbox.integration.mjs. It uses disposable PostgreSQL WASM and no production credentials. It exercises role access, stale competing requests, idempotent retries, source rejection, explicit withdrawal, and rollback on audit failure. It is not yet wired into CI. The final integrated website still needs an isolated-browser interaction check before release.

Public readers may select published candidates; drafts and audit events remain private. Public pages should render escaped plain text/Markdown and carry the complete source list. Adding the first public query must update the D1 provenance manifest for this multi-source editorial artifact.
