# S29 baseline release readiness — 2026-08-30

**Purpose:** prepare one baseline-safe Preview and production decision packet.
This record does not authorize a Preview, production deploy, firewall publish,
email send, migration, production-data change, replay, or billing change.

## Proven release state

- Canonical parent `main` is
  `dff3099d8420da236248640eca3f6aee5ef35ac6`, including the green, independently
  reviewed Vercel Preview target-attestation fix from PR #157 and the
  production-authoritative type-composition fix from PR #160.
- Public production remains Vercel deployment
  `dpl_3Fit9sx7D97BgAbA3iqsRfbjSfUp`, sourced from
  `0ff9fd50443d8d13e15a4d83845b2997cfc1054a`.
- `web/vercel.json` keeps global Git deployment disabled. Opening, updating, or
  merging this PR cannot create a Vercel Preview or production deployment.
- PRs #150, #151, and #153 are merged. They record the Mayor-funding
  retirement chronology, hold unfinished campaign directories through T14,
  and enforce the reviewed three-date July recap hold.
- Draft PR #115 (front-door treatment) and draft PR #140 (public City
  Government Guide) remain outside the baseline. Draft PR #149 remains an
  optional, deferred outreach reference.
- The S29 public-treatment source switch remains off. The baseline therefore
  retains the existing public homepage, navigation, acquisition placements,
  and production-anchor metadata while treatment metadata and public JSON-LD
  remain held. It includes approved reliability, privacy, containment, and
  measurement mechanics.
- `web/src/lib/database.types.ts` carries the production-authoritative
  PostgREST value `14.5`, proven by Schema Drift run 33421053983. The trusted
  Preview controller now composes that one runtime value with exact Preview
  schema bytes instead of committing volatile Preview runtime metadata.
- The fourth and final PR #154 Preview completed successfully at exact
  application head `4e715017247e8cbe192780ef52c8818d66666b51`. The complete
  route, privacy, responsive, health, sitemap, and scoped Amazonbot matrix
  passed; the paid branch, deployment, and all temporary bindings were then
  deleted and independently shown absent.

## Database and model boundaries

- Supabase remains Pro.
- Production migrations 136 and 138 through 146 are recorded live and require
  a fresh read-only ledger/schema verification immediately before production
  approval.
- Migration 134 remains absent, byte-locked, and a HARD NO-GO.
- No migration or production-data correction is part of this PR.
- Production routing remains DeepSeek-first, with Luna limited to the two
  benchmarked exceptions. D2 remains 0.50 and the repository remains AGPL-3.0.

## Current capacity state

The authenticated Vercel Hobby account-wide Usage snapshot at 2026-08-30
23:43 UTC covered Jul 31 through Aug 30 and showed:

- Fluid Active CPU: `5h 39m / 4h` — above the included rolling allowance and
  above the S29 A0 hard-stop threshold.
- ISR Writes: `179K / 200K` — 89.5%, above the 75% S29 start-safe threshold.
- Fast Origin Transfer: `4.55 GB / 10 GB`.
- Fluid Provisioned Memory: `206.9 GB-Hrs / 360 GB-Hrs`.
- Web Analytics events: `3.6K / 50K`.

No Pro upgrade is recommended or authorized. These readings do not forbid a
bounded containment/reliability deployment, but they do forbid recording A0 or
starting an unattended measurement window. After the final CPU-affecting
baseline release, observe at least seven complete UTC days and require the
documented rolling-CPU, recent-rate, ISR, and other capacity gates before A0.

## Consumed Preview attempts — all four safely closed

- The operator's first PR #154 Preview approval was consumed exactly once by
  bootstrap run [33415519449](https://github.com/pjfront/richmond-common/actions/runs/33415519449).
- The data-less Micro branch passed baseline and migration integrity. Its only
  H0 schema-type difference was the generated PostgREST version, so the allowed
  one-file H1 type update was committed and verified.
- H1 run [33415905003](https://github.com/pjfront/richmond-common/actions/runs/33415905003)
  passed the retained-branch, direct-child, exact type-generation, and Schema
  Type Gate checks. It did not complete browser verification: the controller
  rejected Vercel's canonical built-in Preview response, `target: null`, while
  it incorrectly expected the string `preview`.
- Failure cleanup deleted the Supabase branch and all eight exact branch-scoped
  Vercel variables. The one late exact deployment was separately attested,
  deleted, and confirmed absent by exact-ID Vercel lookups. Follow-up cleanup
  run
  [33416516431](https://github.com/pjfront/richmond-common/actions/runs/33416516431)
  found no remaining Supabase branch or branch-scoped Vercel variables. There
  is no continuing branch cost.
- PR #157 fixed the fail-closed attestation to require an explicitly present
  null Preview target while rejecting missing, Production, staging, and custom
  targets. It did not change POST count, retries, timing, identity checks, or
  cleanup ordering, and its controller suite passed 164 tests.

The first approval cannot be reused.

- The operator's second PR #154 Preview approval was consumed exactly once by
  bootstrap run
  [33420831931](https://github.com/pjfront/richmond-common/actions/runs/33420831931)
  against exact H0 `be139feae000496bcaf2b2a8bc16525c81fcb212`.
- It created exactly one data-less Micro branch, `pr-154-preview`, with project
  ref `zejfgksjmrzsofvsqddd`. Baseline, migration, and security verification
  passed. No Vercel deployment was requested.
- The only H0 difference was hosted Preview metadata:
  `PostgrestVersion: "14.5"` became `"14.17"`. The generated file was retained
  as SHA-bound artifact `9768835874`, and exact direct-child H1
  `46f79098cf1dbeaa3dc78f8cfd74c91a881f1a88` changed only that line.
- Verify run
  [33421276025](https://github.com/pjfront/richmond-common/actions/runs/33421276025)
  re-attested the same branch, H0 parent, type-only H1, immutable inventories,
  and active status. A fresh typegen from that same branch still failed the old
  byte comparison. The old workflow did not retain that second raw file, so its
  exact embedded value is unknown and is not inferred here.
- The failed verify run cleaned the branch and all eight exact Vercel variables
  (`supabase_deleted=true`, `vercel_envs_deleted=8`). Follow-up cleanup run
  [33421683297](https://github.com/pjfront/richmond-common/actions/runs/33421683297)
  returned `false/0`, confirming nothing remained and no cost continued.
- PR #160 fixed the contradiction without weakening schema comparison. It
  strictly parses one canonical metadata block, generates production metadata
  before any billable branch can be created, replaces only the quoted Preview
  version span, rejects incompatible major versions, and compares every other
  byte exactly. Malformed production output fails before branch creation; H1
  failures clean before diagnostic upload. Its focused suite passed 191 tests
  and three independent reviews found no remaining blocker.

The second approval also cannot be reused.

- The operator's third PR #154 Preview approval was consumed exactly once by
  bootstrap run
  [33428436954](https://github.com/pjfront/richmond-common/actions/runs/33428436954)
  against immutable H0 `4ae5924a14935c0c23f303c7ed71d4c6c98f3d32`.
- It created one data-less Micro branch, `pr-154-preview`, with project ref
  `txmpojluvxlgpmiabdlf`, and applied the 11 clean-room migrations. Baseline,
  migration, and security checks passed.
- Preview and production PostgREST metadata both resolved to `14.5`; the exact
  composed type-file SHA-256 was
  `07020d3ea8802b9d3574c5c6130b6fcb77d9e5a6cc1bcfe14a1df66c03d3ebd4`.
  The matching SHA-bound artifact is `9771675667`.
- The controller requested exactly one attested Vercel Preview. Deployment
  `dpl_4WJkajpVniB6wjUuBsB31Ets66BU` reached `READY` with the exact approved
  H0. Browser verification confirmed that the public shell, Meetings, Council,
  Elections fallback, About, and subscription form rendered from the empty
  branch without client-console errors or analytics script/intake activity.
- The first held-directory probe exposed a genuine Preview boundary defect:
  anonymous `/pac`, `/unions`, and `/corporations` requests returned a
  production-mode server exception instead of their intended quiet 404. No
  campaign-directory content or production data was exposed. Runtime logs
  proved that the controller correctly withheld `IRON_SESSION_PASSWORD`, but
  the application did not yet translate that exact secretless Vercel Preview
  boundary into an anonymous session.
- Verification stopped at that first broken boundary. The health, sitemap,
  responsive, subscription no-write, and Amazonbot runtime matrix were not
  claimed complete.
- Cleanup run
  [33429379461](https://github.com/pjfront/richmond-common/actions/runs/33429379461)
  deleted the exact branch and all nine branch-scoped Vercel bindings
  (`supabase_deleted=true`, `vercel_envs_deleted=9`). Independent read-only
  checks found zero matching bindings, no matching deployment, and no resolvable
  exact branch ref. The armed watchdog will safely no-op against absent state.

The third approval cannot be reused. This PR now contains the narrow
application fix: only a Vercel Preview with no session secret resolves as
anonymous; Vercel Production and every non-Preview production runtime still
enforce the required secret.

Local validation of that fix passed all 305 web tests, TypeScript, focused
ESLint, and an isolated production build. A secretless Preview-mode production
server returned `{"isOperator":false}` from `/api/operator/session` and quiet
404s from `/pac`, `/pac/[slug]`, `/unions`, `/corporations`, and `/orgs/[slug]`.
Browser verification found no error overlay, horizontal overflow, or held-page
content leak. Independent security review confirmed that Production remains
fail-closed and Preview analytics remain outside the exact production-host
allowlist.

- The operator's fourth PR #154 Preview approval was consumed exactly once by
  bootstrap run
  [33436490400](https://github.com/pjfront/richmond-common/actions/runs/33436490400)
  against immutable H0 `4e715017247e8cbe192780ef52c8818d66666b51`.
- Trusted controller `main@dff3099d8420da236248640eca3f6aee5ef35ac6`
  created exactly one data-less Micro branch, `pr-154-preview`, with project ref
  `reognpvarpzotcctxtmy`, and applied the 11 clean-room migrations. Baseline,
  migration, security, exact-H0 type comparison, and Schema Type Gate checks
  passed. Preview PostgREST metadata was `14.17`; composing the production
  `14.5` runtime literal produced the exact committed type-file SHA-256
  `07020d3ea8802b9d3574c5c6130b6fcb77d9e5a6cc1bcfe14a1df66c03d3ebd4`.
  SHA-bound artifact `9774644012` retains the raw and composed evidence.
- The controller requested exactly one attested Vercel Preview, deployment
  `dpl_8bB7yxNS4eFXJgsSY4mLQds59Qn9`. It reached `READY` on PR #154,
  the exact H0, and Vercel's canonical null Preview target. Only the nine
  expected Preview bindings existed; Production operator credentials were not
  present.
- Authenticated read-only HTTP checks passed every required boundary. Public
  routes rendered; the election and retirement redirects were exact; all held
  campaign-directory routes returned quiet generic 404s without content
  leakage; `/api/operator/session` returned exactly
  `{"isOperator":false}`; `/api/health` reported all ten migration groups
  applied; `robots.txt` and the four-URL baseline sitemap matched policy; and
  only Amazonbot deep item URLs were denied while its meeting/API routes and
  Amzn-SearchBot, Amzn-User, Googlebot, and bingbot controls were unaffected.
- Desktop and 375-pixel mobile browser checks found meaningful empty-branch
  states, no error overlay, no console errors, no horizontal overflow, no held
  navigation or treatment metadata, no form submission, and no analytics
  cookie, storage key, or intake request. Exact-deployment runtime review found
  no 5xx response.
- Standard cleanup run
  [33437902066](https://github.com/pjfront/richmond-common/actions/runs/33437902066)
  completed successfully with `supabase_deleted=true` and
  `vercel_envs_deleted=9`. Independent checks then found the exact deployment
  absent by ID, zero deployments in the test window, and no DNS record for the
  exact Supabase ref. The armed watchdog will safely no-op against absent state.

The fourth approval cannot be reused. No PR #154 Preview approval remains, and
there is no active branch, retained deployment, temporary binding, or continuing
Preview cost.

## Crawler and Preview gates

- The Vercel Firewall currently has a live Preview-only Amazonbot Deny rule and
  a live Production Log rule, with no pending draft.
- Production Deny is not live. The matching application `robots.txt` policy is
  committed but remains absent from the old production deployment.
- The exact-PR Preview verified the Preview deny behavior without Production
  credentials. No additional PR #154 Preview is authorized or needed.
- Before a final baseline production packet, finish the required Production Log
  review and prepare the separate operator-run WAF publish step. Production
  Deny remains unchanged until that evidence and exact command are ready.
- Earlier approvals for PRs #97, #100, #136, and all four PR #154 attempts were
  consumed and cannot be reused.

## Ordered next steps

1. Preserve the completed exact-H0 Preview record and allow only documentation
   evidence to move the draft PR head. Do not request or run another Preview.
2. Review at least seven complete UTC days of the Production Log rule and stage
   exactly one production-deny change if the evidence remains clean. The
   operator executes the final firewall publish command when prompted.
3. Re-verify production migrations and current Vercel usage read-only.
4. Finish PR #154's documentation-only CI and independent evidence review, then
   prepare the focused merge/readiness decision without deploying Production.
5. Prepare the exact-current-main BASELINE decision packet,
   including every change since the pinned production deployment.
6. Only after the operator replies
   `APPROVE PRODUCTION BATCH: <full 40-character BASELINE SHA>`, run the guarded
   exact-SHA deployment and smoke checks.
7. Do not record A0 until the final baseline is soaked and every capacity,
   analytics, canary, and operator-session gate passes.

**ACTION:** None. Do not repeat any PR #154 Preview approval. The next operator
input will be an exact firewall publish command or an exact 40-character
Production batch approval, surfaced only after its evidence packet is ready.
