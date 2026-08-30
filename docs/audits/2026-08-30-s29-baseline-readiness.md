# S29 baseline release readiness — 2026-08-30

**Purpose:** prepare one baseline-safe Preview and production decision packet.
This record does not authorize a Preview, production deploy, firewall publish,
email send, migration, production-data change, replay, or billing change.

## Proven release state

- Canonical parent `main` is
  `ac2f44dd7277b6ae0ff5d2ec94baedc5c85c47cd`, with its exact main-push Build
  Check green.
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

## Crawler and Preview gates

- The Vercel Firewall currently has a live Preview-only Amazonbot Deny rule and
  a live Production Log rule, with no pending draft.
- Production Deny is not live. The matching application `robots.txt` policy is
  committed but remains absent from the old production deployment.
- Before a final baseline production packet, run one fresh exact-PR Preview to
  verify the Preview deny behavior without production credentials, then finish
  the required production-log review and prepare the separate operator-run WAF
  publish step.
- A Preview requires a new approval naming this exact PR. Earlier approvals for
  PRs #97, #100, and #136 were consumed and cannot be reused.

## Ordered next steps

1. Finish this PR's CI and independent review.
2. Ask for one exact two-hour Supabase Micro Preview approval for this PR.
3. Run and clean up the exact Preview; verify Amazonbot denial and the complete
   baseline user journey.
4. Review at least seven complete UTC days of the Production Log rule and stage
   exactly one production-deny change if the evidence remains clean. The
   operator executes the final firewall publish command when prompted.
5. Re-verify production migrations and current Vercel usage read-only.
6. Merge this PR and prepare the exact-current-main BASELINE decision packet,
   including every change since the pinned production deployment.
7. Only after the operator replies
   `APPROVE PRODUCTION BATCH: <full 40-character BASELINE SHA>`, run the guarded
   exact-SHA deployment and smoke checks.
8. Do not record A0 until the final baseline is soaked and every capacity,
   analytics, canary, and operator-session gate passes.

**ACTION:** Reply exactly:
`APPROVE PREVIEW COST: one ephemeral Supabase Micro branch for PR #154, maximum
two hours, then auto-delete.` This authorizes Preview only, not production.
