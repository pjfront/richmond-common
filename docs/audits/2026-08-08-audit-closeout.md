# August 2026 audit closeout

**Date:** 2026-08-08

**Meaning of closeout:** discovery is closed and the execution boundaries are fixed. This is not approval to merge, deploy, apply a production migration, or run an unbounded sync.

## Canonical baseline

- `origin/main`: `3be0709902264bcaeae6bc6e6a0d114299da88f7` (merged PR #83).
- Production Vercel deployment `dpl_2PQXx5cpxhCTcjAiJCJcsxaciX4J` is healthy.
- Supabase is **Pro**. Migrations 126–133 and 135 are live.
- Migration **134 is a hard no-go**. Never apply it and never rewrite it in place.
- The public flag/count threshold remains **0.50**; no D2 threshold change is authorized.
- Model routing is **DeepSeek-first**. OpenAI Luna has exactly two separately benchmarked exceptions: failed negated-motion vote explainers and image-only Form 460 summary recovery. Any broader OpenAI/Kimi route needs its own representative Richmond benchmark.
- **S25 is complete. S26 and S28 are partially shipped.** Broad feature expansion is paused.
- The project remains **AGPL-3.0**; the BSL proposal is retired.

## Closeout findings and gates

1. **Contain unsupported taxonomy.** Production independently showed anonymous HTTP 200 access to both `v_influence_pattern_summary` and `influence_patterns`, including five unsupported labels and aggregate counts. Forward migration 136 revokes `PUBLIC`/`anon`/`authenticated` access while retaining service-role operation. It remains unapplied until the focused PR is approved.
2. **Restore alarms before relying on autonomy.** Alert delivery, the stale cap-revert event, and the Data Quality no-final-JSON failure are containment work, not roadmap polish. Their focused tests and external-account state belong in the pre-merge approval packet.
3. **Prove reconciliation on a recoverable clone.** Follow the [eSCRIBE reconciliation decision packet](2026-08-07-escribe-reconciliation-decision-packet.md): GUID-scoped tri-state outcomes, same-day collision protection, attachment count/hash comparison, bounded cohorts, rollback capture, and exact before/after counts. No unbounded production sync.
4. **Close or explicitly disposition trust gaps.** The $160,807 filing gap, donor spot-checks, candidacy-cycle mismatches, possible duplicate contributions, image-only Form 460 dead letters, and false liveness failures must each end in evidence or a named bounded follow-up.
5. **Measure the whole database surface.** Migration 135 fixed two RPCs, not Supabase idle/growth/RPC behavior generally. Preserve the 24-hour measurement as evidence for the next approval packet.

## Roadmap rebaseline

The next product sprint starts only after the containment and reconciliation gates close. It is **S29: Front Door & November Demand**:

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

No PR was closed by this audit sprint; closure remains an explicit repository write after the focused audit PR is reviewed.
