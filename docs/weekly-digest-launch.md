# Authorized weekly digest launch

Prepared September 6, 2026. This record describes a pending activation, not a completed email send or an active subscriber schedule.

## Authorization and timing

The user explicitly approved one digest test to the existing configured canary inbox, then Monday delivery to eligible opted-in subscribers after verification. The accepted proposal is retained locally at `E:/Projectz/RichmondTransparencyProject/astra-digest-preview/tmp/email-activation-proposal.md`; its sample uses the actual two version-2 publications and fake management links. Do not request the same authorization again.

The first representative completed week is August 31–September 6, 2026 UTC. It becomes selectable at September 7, 00:00 UTC, which is September 6 at 5 p.m. in Richmond. Do not backdate publication, override the server clock, supply a custom recipient or period, or send a different week's test merely to bypass this wait. The planned ongoing subscriber job is Monday 16:30 UTC (9:30 a.m. PDT / 8:30 a.m. PST); it may run later if GitHub delays a scheduled job.

## Current state and preparation

The provider-verification update is deployed at `59615f9ced439f4094e870fa6c57cbf9222451f8`, Vercel deployment `dpl_rfdoTHUgSiMFAT3dXefTG38AGoSH`, following PR184. It adds authenticated, read-only proof for the exact configured canary message while retaining the disabled broadcast gate. The deployment wrapper verified the immutable source, pinned project, main ref, READY state and production alias; a separate authenticated lookup agreed at 20:33 UTC. The preceding resident deployment was `97abc9bd5c4ae81911b90034e2f10823dd5df8af`, `dpl_5QCfFa2CLET6ABPMW4ff9BGqrTc1`. Resolve actual current state again before acting; these are recorded observations, not permanent identity assumptions.

Production migrations 150 and 151 are already applied and their replay/access/data-preservation checks passed. No new migration is needed for activation. The deployed digest broadcast gate is off and the existing weekly workflow is an empty-payload, owner-only canary dispatch. A paired activation change is being prepared on `codex/astra-digest-activation` in `E:/Projectz/RichmondTransparencyProject/astra-digest-activation`. Keep it unmerged and undeployed until the representative canary is verified.

## Resume after the week closes

1. Confirm the current UTC time and read the latest preparation receipt in this task. Check whether a canary has already been attempted for provider key `rc:digest:canary:week:2026-08-31` before making any send. Inspect existing workflow runs and the retained exact attempt record; do not infer “not sent” from missing local output alone.
2. Verify the live deployment and authenticated read-only `/api/email/send-digest` capability. Read only bounded relevant published content and subscriber-consent aggregates. The server must select August 31–September 6. Review any added or changed material before sending; preserve exact publication/source identities and current recipient choices.
3. Use the prepared private `tmp/canary_once.py` caller after its read-only preflight to make one canonical `/api/email/send-digest` request with only `mode: canary`. It attests the production source, reserves a durable local attempt receipt before sending, and retains the exact returned provider ID. Do not also dispatch the manual workflow: these are two ways to call the same canary, not two tests. Use the caller's separate `verify` action to read the authenticated proof for that exact ID. The deployed proof checks the configured destination and sender, then returns only the provider state, subject and body hashes. Compare these with the exact source-checked fixture. Provider acceptance and inbox delivery are distinct; record only what the evidence establishes. An ambiguous outcome or mismatched content stops activation and requires investigation of that attempt, not another send.
4. Once verified, finish review of the paired code-gate, Monday workflow, and public-copy change. Preserve the existing ledger, consent-aware claim, publication validation, provider idempotency key, delivery limits and recovery. Complete required CI on the exact reviewed commit, merge, then deploy immutable current main with the existing `web/scripts/deploy-prod.ps1` gate from the clean main checkout. No subscription, sender, canary-address or billing change is authorized.
5. Verify production identity, health, activated capability, public cadence copy and the single Monday workflow. Record the exact canary result, application source, deployment ID and first expected subscriber run. A subscriber with no eligible content receives no digest.
6. Finish this one-time launch follow-up once the activation is verified. Do not leave a recurring Codex launch task running alongside the application's Monday job. Report completion or the specific failure needing attention; do not repeat unchanged status.

The one-time Codex follow-up `finish-richmond-weekly-email-launch` is scheduled in this task for September 6 at 5:10 p.m. Richmond time. It needs this computer and the desktop app running. It is distinct from the prepared GitHub-hosted Monday subscriber workflow, which is not yet active. The private preparation record contains the exact held PR and deployed proof revision. No canary has been attempted during preparation.

## Delivery stop

Disable the weekly workflow schedule and broadcast code gate. Those switches do not stop already queued digest recovery. If a full delivery stop is necessary, briefly pause existing email recovery, use the guarded ledger RPC to put only retryable digest deliveries into manual review, then resume other recovery. Preserve subscriber records and preferences. Already claimed provider sends cannot be recalled. No rollback was performed while preparing this record.

## Evidence

The existing automated API/database suites cover signup, preference changes, consent, unsubscribe/reactivation, publication changes and retry behavior with mocked providers and disposable PostgreSQL. Live forms have not been submitted during this work. The forthcoming representative canary is the live provider check; do not claim an actual subscriber signup rehearsal or subscriber broadcast from those tests.

Keep private provider responses, addresses, credentials and management tokens out of Git and user-facing logs. Public or committed receipts should contain only sanitized identities, aggregate results, source links and verification outcomes.
