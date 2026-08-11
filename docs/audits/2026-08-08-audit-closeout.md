# August 2026 audit closeout

**Opened:** 2026-08-08

**Closed:** 2026-08-10

**Meaning of closeout:** the containment execution sprint is complete and the
remaining boundaries are explicit. This is not approval for the remaining
production corrections, another migration, or an unbounded sync.

## Canonical baseline

- `origin/main`: `e6483290edd46773e3399048901da495df5e7dd7`
  (merged PR #85; the main containment/reconciliation change landed in PR #84).
- Production Vercel deployment `dpl_2PQXx5cpxhCTcjAiJCJcsxaciX4J` remains
  healthy. PR #85 changed workflow/Python code only, so no replacement web
  artifact was required or created.
- Supabase is **Pro**. Migrations 126–133, 135, and approved forward migration
  136 are live. Post-apply checks proved migration 136 present and migration
  134 absent.
- Migration **134 is a hard no-go**. Never apply it and never rewrite it in place.
- The public flag/count threshold remains **0.50**; no D2 threshold change is authorized.
- Model routing is **DeepSeek-first**. OpenAI Luna has exactly two separately benchmarked exceptions: failed negated-motion vote explainers and image-only Form 460 summary recovery. Any broader OpenAI/Kimi route needs its own representative Richmond benchmark.
- **S25 is complete. S26 and S28 are partially shipped.** Broad feature expansion is paused.
- The project remains **AGPL-3.0**; the BSL proposal is retired.

## Closeout findings and gates

1. **Unsupported taxonomy contained.** Migration 136 removed anonymous,
   authenticated, and `PUBLIC` access to `influence_patterns` and
   `v_influence_pattern_summary` while preserving the service-role path. It
   did not delete data or touch migration 134.
2. **Resend handoff and Data Quality bounds are verified.** The stale cap-revert event is completed,
   and the first post-key Alerting run
   [31293564387](https://github.com/pjfront/richmond-common/actions/runs/31293564387)
   passed; Resend accepted the message as
   `11b1ebb5-f829-4181-b361-87e77753d180`. Inbox receipt remains an operator-side
   confirmation. PR #85 gives Data Quality one bounded non-thinking DeepSeek
   retry plus a 10-minute job ceiling. Post-merge run
   [31424483621](https://github.com/pjfront/richmond-common/actions/runs/31424483621)
   passed every step in 1m59s and, with `create_decisions=false`, created zero
   self-assessment decisions.
3. **Reconciliation proof is bounded, not a production-sync authorization.**
   The recoverable clone exercised GUID-scoped tri-state outcomes, same-day
   collision protection, attachment inventory/hash checks, and immediate
   idempotent replay. Current-code clone replay passed; the live cohort's
   minutes-owned attachment preservation was a vacuous 0-to-0 check, with the
   non-vacuous ownership behavior enforced in tests. Rollback artifacts are
   correctly labeled non-restorative partial-delta evidence.
4. **Trust gaps have explicit dispositions.** Filing 216779708's `$160,807.33` gap is
   proven unitemized; three donor lines match their official source; both
   image-only Form 460 summaries were recovered on the benchmarked Luna route;
   candidacy checking has seven `NULL`-cycle provenance gaps rather than a
   proven mismatch; and liveness is 28/32 with each remainder classified.
   The apparent 10 duplicate warning was a `LIMIT 10` reporting bug: the exact
   cohort is 42 duplicate contribution pairs / `$14,900`, proven by a guarded
   42-to-0-to-42 rollback transaction. No duplicate row was deleted.
5. **The bounded 43-hour measurement is complete.** The scheduled task did not
   run, so the same read-only statement was run manually at a
   43h18m endpoint. Database size grew `17,137,664` bytes, temporary files grew
   `12,856,490,870` bytes, and cumulative idle-in-transaction time grew
   `42,607,764.862` ms despite neither endpoint having a live idle-in-transaction
   backend. Migration 135's two RPCs showed only three low-cost flag-count calls
   and no controversial-item calls. Broader RPC cost and grants remain open.

## Remaining explicit gates

- Migration **134 stays forbidden**; it is not a candidate for repair or
  approval.
- Deleting the 42 adjudicated contribution extras requires a separate exact
  production approval. The warning remains intentionally open.
- Any eSCRIBE production replay, correction, rollback, or enforcement migration
  requires a fresh exact GUID-scoped approval packet. No broad sync is allowed.
- Anonymous/internal RPC grant cleanup needs a separate tested forward migration
  and operator approval. The 43-hour temporary-file and transaction-idle growth
  also merit a bounded operations investigation.
- The NextRequest visibility-enum failure is a remaining ingestion defect and
  belongs in a focused repair task.

## Roadmap rebaseline

The next product sprint is **S29: Front Door & November Demand**. Run it in a
fresh task so audit evidence and product judgment do not share a working branch:

- simplify the public front door;
- publish Richmond 101 after voice review;
- finish SEO entry points and structured metadata;
- put subscriptions on the main acquisition paths and complete dependable recap/digest delivery;
- establish privacy-preserving analytics; and
- run bounded November election-season demand tests, then choose the following sprint from visits, subscriptions, repeat use, and source mix.

S29 explicitly excludes broad S26/S28 expansion, public scanner-taxonomy work, multi-city abstractions, and donation conversion before trust/demand evidence.

## Stale pull-request triage

| PR | Evidence | Preserved work | Recommendation |
|---|---|---|---|
| [#69](https://github.com/pjfront/richmond-common/pull/69) | Open, non-mergeable, 89 changed files. Its intended general-election `committee_id` propagation, audit `--fix`, migration 121, migration 119 note, and alert-suppression update are already represented on current `main`; direct branch-vs-main comparison found no difference in those core files. | None needed; shipped implementation is already canonical. | Close as superseded. Do not merge the contaminated branch. |
| [#23](https://github.com/pjfront/richmond-common/pull/23) | Open and technically mergeable but based on May state. Adds a 251-line Claude-Code-only phrase-regex Stop hook with a documented false positive and edits a substantially changed `.claude/settings.json`; it cannot enforce current Codex/AGENTS sessions. | Intent preserved as `H.14` in `docs/PARKING-LOT.md`: future platform-native, catalog-aware judgment-boundary enforcement. | Close as obsolete; do not merge verbatim. |
| [#12](https://github.com/pjfront/richmond-common/pull/12) | Draft, non-mergeable, one stale documentation change. The CPRA payee/employer/address cross-reference is unique and still potentially valuable, but its thresholds were exploratory and it belongs after source reconciliation/entity-resolution proof. | Preserved as `B.63` in `docs/PARKING-LOT.md`. | Close after this preservation lands. |

No stale PR was closed by this audit sprint. Their recommendations remain
explicit repository writes after this closeout lands.
