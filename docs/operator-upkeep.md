# Richmond Commons contained-operations checklist

_Status checkpoint: 2026-08-24. This is the short owner manual. Technical alert
handling lives in [operator-alert-playbook.md](operator-alert-playbook.md)._

## The steady-state contract

The operator should not need to open GitHub, Vercel, or Supabase every day.
Richmond Commons owns routine ingestion, health checks, bounded retries,
backups, delivery ledgers, and status summaries. The operator owns the few
actions that require an account login, public judgment, new spending, or an
irreversible production decision.

There is no routine requirement for a $100/month coding-agent subscription.
Normal operation uses the existing hosted stack and the separately capped LLM
API budget. A technical alert includes a copy-ready handoff suitable for a
general $20/month assistant with repository context. When an existing check
detects an unfamiliar failure, it says clearly that engineering help may be
needed. Monitoring cannot promise to detect every unknown failure.

## What automation owns

| Work | Normal behavior | Operator notification |
|---|---|---|
| Site and pipeline health | Daily bounded homepage, API, liveness, routed-LLM-spend, and civic-calendar checks | Weekly/monthly status; immediate action-formatted email for a current failure |
| Workflow failures | Production workflows are wrapped without executing failed-run code | One deduplicated `ACTION:` email plus a best-effort GitHub issue audit trail |
| Source ingestion | Existing bounded GitHub Actions schedules and idempotent enrichment paths | Only failures or stale expectations require action |
| Agenda previews | Existing per-recipient ledger prevents duplicate successful sends | Delivery failures use the workflow alert contract |
| Email recovery | At most 50 due welcome, orientation, recap, or digest rows per request | Failure alert says not to resend or edit subscriber rows |
| Database backup | Encrypted weekly backup with round-trip verification | Wrapped workflow failure alert |
| Privacy analytics | Cookie-light Vercel Web Analytics and bounded S29 checkpoints | Private action-formatted checkpoint packet |

Vercel and Supabase plan usage are not part of the routed LLM cost check. Until
a stable bounded provider-usage reader is proven, the operator must complete a
separate monthly dashboard check described below. The system must not describe
that manual check as automated monitoring.

## What the operator owns

1. **Read the first `ACTION:` line of a Richmond Commons alert.** If it says
   `None`, no reply or technical work is needed.
2. **Complete account-only actions.** Passwords, passkeys, one-time codes,
   billing cards, registrar renewals, and Cloudflare/GitHub/Vercel account
   confirmations stay with the operator. Never paste those secrets into an AI
   chat or issue.
3. **Choose public framing.** Voice, labels, publication graduation, and other
   community-facing judgment stay human.
4. **Approve a named production batch.** Merging is not deploying. Before a
   production deploy, require an exact source SHA and a plain-language list of
   resident-visible changes; reply `APPROVE PRODUCTION BATCH: <full SHA>` only
   when that packet is correct.
5. **Approve human-boundary production work separately.** Production-data
   corrections or replays, cost increases, and firewall publishes never
   inherit a general code or deploy approval. Migration 134 remains a hard
   no-go. Routine migration authoring, review, testing, and execution may be
   delegated under the project catalog; they do not create a new recurring
   approval chore, although the exact production batch still needs approval.
6. **Look at one canary message before subscriber automation is activated.**
   Confirm that the subject, source disclosure, links, and unsubscribe wording
   are correct. The canary address stays in encrypted provider configuration,
   not in the public repository.
7. **Complete the monthly provider-capacity check until it is automated.** Use
   the signed-in Vercel and Supabase dashboards; do not paste billing details,
   access tokens, or subscriber data into an issue or AI chat.

## What to do when an alert arrives

1. Read only the first `ACTION:` line initially.
2. If it says **None**, archive the email.
3. If it gives click-by-click steps, complete those steps and stop.
4. If it includes **COPY/PASTE MESSAGE FOR YOUR CODING ASSISTANT**, remove any
   secrets or private resident information, then paste that whole block into
   Codex, ChatGPT, Claude, or another capable coding assistant.
5. Do not repeatedly rerun a failed sync, resend email, edit subscriber rows,
   apply a migration, or publish a firewall rule unless the action packet
   explicitly proves that operation is safe and authorized.

Provider-generated notices may not follow Richmond Commons formatting. Use the
provider-message prompt in
[operator-alert-playbook.md](operator-alert-playbook.md#provider-messages).

## Remaining one-time setup

### 1. Arm the outside dead-man's switch

**ACTION:** Follow the eight Healthchecks.io steps in
[Alerting stopped](operator-alert-playbook.md#alerting-stopped). The missing
`HEALTHCHECKS_PING_URL` repository secret is the reason raw GitHub Actions mail
must remain enabled today.

After the check is **Up** and the Richmond-owned channel test arrives, follow
[Stop duplicate raw GitHub Actions mail](operator-alert-playbook.md#stop-duplicate-raw-github-actions-mail).

### 2. Finish the Cloudflare account-only checks

**ACTION:** Sign in to the Cloudflare dashboard with the existing account. In
**Email → Email Routing → Routing rules**, verify that the `hello` address is
**Active** and targets the already approved forwarding inbox. Send one ordinary
test email to `hello@richmondcommons.org` and confirm it arrives. Do not put the
private forwarding destination in a public issue or repository file.

If the route is inactive or the test message does not arrive, do not delete or
recreate routing rules. **ACTION:** Remove any private address, token, and
account detail from the Cloudflare error, then paste it after the
[Provider messages](operator-alert-playbook.md#provider-messages) prompt and
ask for account-safe click-by-click diagnosis.

DMARC is already publicly verified at `p=none`; keep it in observation mode
until legitimate sender coverage is confirmed.

### 3. Publish the staged production observation + Preview Deny rules

The Vercel Firewall production publish command is deliberately operator-only.
The 2026-08-24 read-only checkpoint recorded exactly two staged changes: add the
production observation rule, and change the original Amazonbot rule from
production Log to preview Deny. Recheck the draft immediately before publishing;
the dated observation is not permission to publish a different draft.

**ACTION:** In PowerShell, run these read-only commands first:

```powershell
$env:NO_UPDATE_NOTIFIER='1'
$env:NPM_CONFIG_REGISTRY='https://registry.npmjs.org/'
$env:VERCEL_ORG_ID='team_EZvKrao9Jh9nwoKNX648v4qy'
$env:VERCEL_PROJECT_ID='prj_Y0sIBsC2DKkl4lsoKbS11Y3cFTz4'
npx --yes vercel@59.1.4 firewall rules inspect "S29 Amazonbot production observation" --scope phillips-projects-1f180556
npx --yes vercel@59.1.4 firewall rules inspect "S29 Amazonbot item containment" --scope phillips-projects-1f180556
npx --yes vercel@59.1.4 firewall diff --scope phillips-projects-1f180556
```

The first inspect command must show the production-observation rule as
**Enabled** with **Action: Log** and all three conditions combined:

1. **Environment equals production**.
2. **Raw Path matches** `^/meetings/[^/]+/items/[^/]+/?$`.
3. **User Agent contains** `Amazonbot/0.1`.

The second inspect command must show the item-containment rule as **Enabled**
with **Action: Deny** and the same Raw Path/User Agent predicates, but with
**Environment equals preview**. Rule IDs may differ and do not need to be
copied.

The diff must then show exactly:

1. `Added rule "S29 Amazonbot production observation"`.
2. `Modified rule "S29 Amazonbot item containment"`, changing **Log → Deny**,
   adding **environment equals preview**, and removing **environment equals
   production**.

If any command fails or anything differs, stop before publishing.

**ACTION:** Do not publish or improvise another command. Remove tokens and
private account data from the output, then paste it after this message in a
coding assistant:

```text
I maintain Richmond Commons (https://richmondcommons.org), a Richmond,
California civic transparency site in
https://github.com/pjfront/richmond-common. A pinned, read-only Vercel Firewall
rules inspect or diff did not match the expected two-rule Amazonbot Preview
draft. Diagnose the supplied output without publishing, discarding, editing,
enabling, disabling, or reordering any firewall rule. Preserve the production
Log observation rule and the Preview-only Deny staging sequence. Return one
plain-language explanation and one exact ACTION line for the operator.
```

If both inspected rules and the diff match exactly, run:

```powershell
$env:NO_UPDATE_NOTIFIER='1'
$env:NPM_CONFIG_REGISTRY='https://registry.npmjs.org/'
$env:VERCEL_ORG_ID='team_EZvKrao9Jh9nwoKNX648v4qy'
$env:VERCEL_PROJECT_ID='prj_Y0sIBsC2DKkl4lsoKbS11Y3cFTz4'
npx --yes vercel@59.1.4 firewall publish --yes --scope phillips-projects-1f180556
```

If it succeeds, report `PREVIEW DENY PUBLISHED` so the Amazonbot and
normal-browser preview tests can be prepared before any production Deny is
staged. Publishing the rule does not create a READY Preview deployment. If no
READY Preview exists for the exact reviewed PR/SHA, the next packet will ask
for a new, PR-specific ephemeral Supabase Micro approval (maximum two hours,
then deletion). Earlier PR #97/#100 approvals are spent and cannot be reused;
no branch or Preview may be created without the new exact approval.

This publish does **not** finish production containment. After the Preview
tests pass and at least seven complete UTC days of production Log observation
are reviewed, the operator will receive a new packet with fresh rule-inspect,
diff, and publish commands for production Deny. Every production Firewall
publish remains operator-only. Do not reuse today's command, output, or
approval for that later publish.

If publishing fails or the result is ambiguous, **ACTION:** Do not rerun the
publish command. Use the same copy-ready firewall message above, append the
sanitized publish output, and ask the coding assistant to inspect current rule
state read-only.

### 4. Finish the held public-UX batch

The operator approved PR #115's static navigation, visible actions, and
truthful subscription cadence, and approved PR #111's detail-only trust
boundary and recommended commit framing. The missing D1 provenance quartet on
legacy aggregate index rows remains a publication blocker, so the aggregate
index rewrite stays out. Coding sessions may finish, test, and merge those
reviewed commits; merging is still not deploying.

**ACTION:** None today. Wait for the baseline/treatment release packet. Do not
approve a current-main deployment merely because these PRs merge: their visible
changes belong after the 14-day untreated baseline is frozen. This approval
does not authorize invented timestamps, generic portal links presented as
exact sources, or a production-data backfill.

### 5. Review Richmond 101 before public graduation

Richmond 101 is merged only as an operator-only, `noindex` page. It is absent
from public navigation and the sitemap. Public graduation requires a human
decision about voice, tone, framing, source coverage, and navigation placement;
passing code tests cannot make that community-facing judgment.

**ACTION:** Wait for the Richmond 101 screenshot/source packet. Review it as a
Richmond, California resident, then reply either
`APPROVE RICHMOND 101 GRADUATION` with any wording or navigation changes, or
`KEEP RICHMOND 101 OPERATOR-ONLY` with the reason. Neither reply approves a
deployment; no public route changes should be made before this decision.

### 6. Approve the baseline and treatment as separate exact batches

The operator accepted the exact-ID rollback policy: every emergency rollback
requires a new approval naming one exact Vercel deployment ID, and a Vercel
rollback never reverses database migrations or data changes. That policy does
not approve any rollback or production deployment.

Current `main` already contains held visible SEO/sitemap work, while the
measurement contract requires 14 complete untreated baseline days. Therefore
the next release cannot simply deploy whatever SHA happens to be current. A
coding session must first prepare and independently verify a baseline-safe
exact SHA containing required non-visible reliability/privacy behavior and the
matching Amazonbot policy while holding every visible S29 treatment. The
operator then receives two separate packets:

1. the exact baseline SHA and rollback deployment;
2. only after B14 is frozen, the exact visible-treatment SHA and its baseline
   rollback deployment.

**ACTION:** None today. Do not approve a production SHA until its packet labels
it **BASELINE** or **TREATMENT**, lists the exact full SHA and rollback
deployment ID, and proves that the phase boundary is ready. After that exact
approval, the deployment command is delegated; the operator does not need the
Vercel CLI.

### 7. Confirm the weekly-digest canary

The proposed first subscriber-digest release is a typed trusted-main canary and
must remain code-disabled for broadcast. It has no cron. This is a release gate,
not a description of current production: do not trigger it until the canary PR,
its independent review, and the exact production batch are complete. After that
release is deployed and the encrypted canary address is configured, the trusted
event makes one provider-idempotent test attempt. Resend retains that
idempotency key for 24 hours; it is not a durable exactly-once ledger. Never
trigger it again after a missing or ambiguous result until the inbox and Resend
sent-email log have been checked.

The originally approved plus-address appeared in an earlier tracked runbook and
therefore remains visible in Git history even after current-tree redaction.
Recommended treatment: use a fresh plus-address for the production canary.

**ACTION:** Before the exact production deploy, open **Vercel → rtp → Settings
→ Environment Variables**, add `SUBSCRIBER_CANARY_EMAIL` for **Production**
using a fresh private plus-address, and save it. Do not put the address in a
repository file or issue. Reply only `CANARY ADDRESS SET`; do not paste the
address. Environment changes apply only to the next deployment.

After the approved exact deployment reports the read-only digest capability as
`canary_ready: true` and `broadcast_ready: false`, **ACTION:** Reply
`APPROVE DIGEST CANARY DISPATCH`. That authorizes one owner-only empty-payload
event and exactly one provider-idempotent attempt to the configured canary
address. It does not authorize a retry, a subscriber broadcast, or the Monday
schedule. A coding session can send the typed event; no CLI work is required
from the operator.

**ACTION:** Reply `DIGEST CANARY LOOKS GOOD` only after the message arrives and
the subject, source disclosure, links, and footer are correct. A separate small
change can then add the Monday completed-week schedule.

If the environment variable cannot be saved, or the canary is missing or has
an ambiguous provider result, **ACTION:** Do not trigger or resend it. Remove
the private address and tokens, then use the copy-ready
[Subscriber email delivery](operator-alert-playbook.md#subscriber-email-delivery)
handoff with the deployment URL and sanitized Resend/Vercel result.

## Routine upkeep after setup

- **Daily:** none, unless an `ACTION:` alert arrives.
- **Weekly:** skim the Richmond Commons status email. `ACTION: None` means
  archive it.
- **Monthly:** read the private monthly summary for routed LLM spend, subscriber
  count, oldest alert, and calendar horizon. Then open **Vercel → rtp → Usage**
  and **Supabase → Organization → Usage**. Confirm Vercel Active CPU is fewer
  than 180 rolling minutes and the trailing seven-day average is at most four
  minutes/day; confirm every other Vercel hard quota remains below 75%; confirm
  Supabase database size and egress remain below 75%. If any threshold fails,
  take no upgrade or replay action—copy the dashboard period, resource name,
  used amount, limit, and this manual URL into a coding assistant and ask for a
  read-only diagnosis and an action-first decision packet.
- **When a provider asks:** update a billing card, renew a domain, or confirm an
  account using the provider's own signed-in dashboard—not a link requesting
  secrets in an unexpected message.
- **Before public changes:** decide framing and approve the exact production
  SHA. Routine tested backend fixes may merge without a click, but remain
  undeployed until the named batch is approved.

## Cost and capacity checkpoint

Snapshot from the
[2026-08-24 contained-operations evidence](audits/2026-08-24-contained-operations-evidence.md):

- **Vercel:** Hobby remains the recommended plan; Pro is not needed. Last-30-day
  transfer, requests, ISR operations, function calls, memory, build minutes,
  and analytics were below Hobby limits. Active CPU was the exception at about
  5h13m against 4h, almost entirely Richmond Commons traffic. Architecture and
  Amazonbot containment must lower this before any upgrade is reconsidered.
  A fresh CLI check found no production error logs or HTTP 500s in the prior 24
  hours. Vercel listed 89 failed Preview deployments since August 7, with about
  477 seconds of build-machine time in total. A sampled run failed closed at
  the intentional environment gate because it lacked an approved isolated
  Supabase Preview environment; the other failures were not individually
  attributed by this audit. Production was not unhealthy. Vercel's CLI metric
  queries require paid Observability Plus, which is not needed for this
  low-maintenance plan.
- **Supabase:** Pro remains necessary and approved. The current database was
  about 1.08 GB of the 8 GB allowance, and organization egress about 8.6 GB of
  250 GB. No preview branch was active. Historical preview-branch compute in
  the current billing period was about 261 hours / $3.51.
- **Preview policy:** one explicitly approved ephemeral Supabase Micro branch
  at a time, exact PR and SHA, maximum two hours, then deletion. No production
  data clone.
- **LLM pipeline:** DeepSeek-first; only the two benchmarked Luna exceptions.
  The unattended monthly API cap remains $5 unless the operator explicitly
  changes it.
- **Cloudflare and analytics:** remain on the no-upgrade path for the November
  test.

## November completion gates

Richmond Commons is contained for the November test when all of these are true:

1. Amazonbot item-route containment is tested in Preview, observed in
   production for at least seven complete UTC days, and only then changed to
   production Deny. The matching robots policy is part of the baseline-safe
   application release.
2. The exact baseline-safe application is deployed without the visible S29
   treatment and soaks for at least seven complete UTC days. A0 starts only
   after Vercel Active CPU is fewer than 180 rolling minutes, the trailing
   seven-day average is at most four minutes/day, each of the latest three
   complete days is below four minutes, and the other documented gates pass.
3. 14 complete untreated UTC days are captured and frozen as B14 before
   any front-door, public navigation, subscription-placement, public SEO, or
   sitemap treatment deploys. Pre-A0 traffic is never relabeled as baseline.
4. The final front door and detail-only feature cut then deploy as one reviewed
   treatment batch; unfinished or unattributed campaign aggregate views are
   not silently presented as complete. The approved rolling 24-month
   agenda-item sitemap remains in this held treatment unless the runbook's
   separately reviewed CPU exception is invoked before A0.
5. Richmond 101 passes operator voice/source review before any public
   graduation.
6. Subscriber canary passes, followed by idempotent Monday weekly digests and
   the already automated pre-meeting previews.
7. Fourteen complete treatment UTC days are captured through T14. Reporting
   uses pageviews, visitor-days, initial subscriptions, and reactivations; it
   never claims cross-day unique or returning residents.
8. The bounded test runs without cookies, custom analytics events, a paid
   analytics add-on, or a Vercel Pro upgrade.
9. The October 1 active donation ask remains on hold through T14 and until its
   documented audience and zero-touch reliability gates are met.
10. Every remaining alert has one clear action or a copy-ready technical
    handoff.

Standing constraints remain: Supabase Pro; DeepSeek-first with only the two
benchmarked Luna exceptions; AGPL-3.0; D2=0.50; migration 136 live; migration
134 HARD NO-GO; no broad S26/S28 expansion, unbounded sync, or production-data
correction under this plan.
