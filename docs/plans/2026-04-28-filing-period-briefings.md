# Filing-Period Briefings — Plan

_Source: this plan was developed in plan mode at `/root/.claude/plans/scope-this-i-want-twinkly-whale.md` and committed here so it travels with the repo._
_Date: 2026-04-28 · Branch: `claude/campaign-finance-alerts-lq07d`_

## Context

Q1 2026 closed 2026-04-24. Richmondside published a filing-period briefing on 2026-04-27 covering Richmond's mayoral and council races. Two failures surfaced on Richmond Commons in the comparison:

1. **Wrong totals.** Anderson's page understates by ~$14k because he files on paper, and `src/data/paper_filings/anderson_mayor_2026.json` was last hand-edited on 2026-04-10. F497P1/F497P2 (24-hour reports, types 20/21) are also disabled in `src/data_sync.py:85`.
2. **Wrong shape.** The signals the article surfaces — out-of-town money, cross-candidate donor clustering, deadline bursts, vendor-related giving — are fundraising-pattern signals. Our `conflict_scanner.py` is vote-anchored. It can't see them by construction.

## The unifying frame

The platform already generates **briefings** for civic events:

- `post_meeting_recap.py` — completed meetings (retrospective).
- `generate_orientation_previews.py` — upcoming meetings (prospective).
- `decision_briefing.py` — pending operator decisions.

Each follows the same shape: trigger → source-closest evidence → structured generation → tier outputs by publication readiness → operator review → render to UI.

**Filing-period briefings are the missing third member of this family.** The Richmondside article *is* a filing-period briefing produced by a human reporter on the natural cadence (Q1 closes April 24 → article publishes April 27). We don't produce one. That's the actual gap.

This frame collapses the four problems into one pipeline:

| Symptom | What it is in the briefing frame |
|---|---|
| Wrong totals (paper PDFs, F497 disabled) | The briefing's **evidence base** is incomplete. |
| Wrong scanner shape | We have no **briefing generator** for filings. |
| Existing scanner is noisy | The meeting briefing's input-filter is uncalibrated — same Tier model fixes both. |
| Display gap | The briefing rendered. Candidate page = per-candidate sections. Dashboard = cross-candidate sections. **One artifact, two views.** |

The existing `conflict_scanner.py` isn't "demoted" — it's **integrated** as the meeting-briefing's analytical step, where its outputs get tier-filtered before publication. Same scanner, better home, no adversarial reframing needed.

## Pipeline shape (mirrors `post_meeting_recap.py`)

```
1. Trigger        → Filing period closes (or 24-hour report fires)
2. Evidence       → contributions + committees + candidates + vendors + permits + form700
                    (source-closest: NetFile API + extracted paper PDFs, never derivatives)
3. Generate       → Briefing components per signal-significance-spec Tier model:
                    Tier A (legal threshold)  → published with citation
                    Tier B (pattern)          → published when pattern_confidence ≥ 0.8
                    Tier C (connection only)  → operator-only draft notes
4. Operator review → Framing-sensitive sections (judgment-boundary catalog)
5. Publish         → Same briefing rendered two ways:
                       • candidate page (per-candidate sections)
                       • /elections/[slug]/finance (cross-candidate sections)
```

## What we build

### Stream 1 — Evidence base (the briefing must have current data)

| Item | Where | What |
|---|---|---|
| Paper-PDF auto-extractor | `src/netfile_paper_extractor.py` (new) | Reuses `identify_paper_filers()` and `download_paper_filing()` in `src/netfile_client.py:334-396`. PyMuPDF (fitz) extracts form 460 Schedule A/E + form 497 text; Claude API (`temperature=0`, tool_use) parses to JSON matching the existing `src/data/paper_filings/*.json` schema. Output drops into `src/data/paper_filings/` — `src/load_paper_filings.py` ingests with no changes. Idempotent on `filing_id`. |
| Re-enable F497P1/F497P2 | `src/data_sync.py:85`, `src/netfile_client.py:431` | `CONTRIBUTION_TYPES = [0, 1, 20, 21]`. Wrap each `fetch_all_transactions(type_id)` in 4-attempt exponential backoff (2/4/8/16s) per project Git Operations convention. On final failure: log + continue (don't fail whole sync). |
| Hook into sync | `src/data_sync.py:61` (`sync_netfile`) | Run paper extractor after electronic fetch, before `load_contributions_to_db()`. |
| Mapping audit | `src/audit_committee_mapping.py` (new) | Reuses patterns from `src/verify_donor_data.py` (added 2026-04-25). Reports orphan committees, candidates without committees, and contributions that exist in DB but don't surface on candidate page query. Decision queue entries per orphan. Promoted to recurring liveness check. |
| Manual one-shot | (operator action) | Refresh Anderson paper filing through 2026-04-24 by hand the day Stream 1 lands so the public site stops being wrong before A1 fully ships. |

### Stream 2 — Briefing generator + display

| Item | Where | What |
|---|---|---|
| Briefing generator | `src/filing_period_briefing.py` (new) | Parallels `post_meeting_recap.py`. Single CLI: `python filing_period_briefing.py --period 2026-Q1`. Writes `meetings`-style row to a new `filing_period_briefings` table with structured JSONB sections + provenance metadata. |
| Briefing batcher | `src/generate_filing_briefings.py` (new) | Parallels `generate_meeting_recaps.py`. Iterates filing periods, regenerates briefings, idempotent. |
| Briefing sections (per candidate) | inside generator | F1 totals · F2 geography (zip prefix: 9480x/9481x = Richmond, broader Bay Area, CA, out-of-state — dollar shares not counts) · F3 industry/PAC concentration · F4 self/related-party · F6 24-hour deadline burst · F7 filing compliance |
| Briefing sections (cross-candidate) | inside generator | F5 cross-candidate donor clustering (factual: "Donor X gave to N candidates totaling $Y" — no inference) · cross-race totals · cross-race geography aggregate |
| Pattern signals (tier-aware) | inside generator | F8 vendor-employee donations · F9 Levine Act exposure on contribution side (active vendor with city contract ≥ Levine threshold → new contribution from anyone at that vendor). Both default Tier C; promoted by operator review. |
| Tier model adoption | `src/migrations/098_proceeding_type.sql`, `src/migrations/099_briefing_tiers.sql` | Implements `signal-significance-spec.md`: `agenda_items.proceeding_type` (entitlement/legislative/contract/appointment/uncertain), briefing-section significance tier (A/B/C). Heuristic-first, LLM-fallback for proceeding type. |
| Existing scanner integration | `src/conflict_scanner.py` (kept, not renamed) | Outputs flow into the **meeting briefing** with the same Tier filter. No separate "scanner UI" anymore — flags appear inside the meeting briefing's analytical section, tier-gated. |
| Candidate page sections | `web/src/app/elections/[slug]/candidates/[name]/page.tsx`, `web/lib/queries.ts`, `web/lib/types.ts` | Renders the per-candidate sections of the latest briefing. Uses `COLS_*` projection (no `select('*')`). All blocks carry `source_url`, `extracted_at`, `source_tier`, `confidence_score` per design rule D1. |
| Filings dashboard | `web/src/app/elections/[slug]/finance/page.tsx` (new) | Renders the cross-candidate sections of the same briefing. Period selector defaults to latest. ISR 1hr (root layout default). |

### Framing rules (non-negotiable)

Per `docs/research/financial-disclosure-framing.md`:
- All sections default to SAFE tier framing.
- No juxtaposition of donations next to specific votes without explicit operator approval. The briefing **structurally** separates fundraising patterns (filing-period briefing) from vote-correlation (meeting briefing) — which itself reduces the defamation-by-implication risk.
- AI-generated narrative copy is labeled (design rule D5).
- Cross-candidate clustering (F5) and Levine-side (F9) require operator review before public publication (judgment-boundary catalog).

## Critical files

**New:**
- `src/netfile_paper_extractor.py`
- `src/filing_period_briefing.py`
- `src/generate_filing_briefings.py`
- `src/audit_committee_mapping.py`
- `src/migrations/098_proceeding_type.sql`
- `src/migrations/099_briefing_tiers.sql`
- `web/src/app/elections/[slug]/finance/page.tsx`
- `tests/test_filing_period_briefing.py` (article-as-oracle harness)
- `tests/test_netfile_paper_extractor.py`

**Modified:**
- `src/data_sync.py` (re-enable types 20/21, plug paper extractor in)
- `src/netfile_client.py` (argparse default for transaction types)
- `src/conflict_scanner.py` (Tier model — keep file name and class names)
- `web/src/app/elections/[slug]/candidates/[name]/page.tsx`
- `web/src/lib/queries.ts`, `web/src/lib/types.ts`
- `docs/pipeline-manifest.yaml` (new sources, queries, pages, expectations)
- `docs/PARKING-LOT.md`, `CLAUDE.md` "What's Built"

**Reused, not modified:**
- `src/load_paper_filings.py` — already loads `src/data/paper_filings/*.json`. New extractor outputs into the same schema.
- `src/netfile_client.py:334-396` — RSS, paper-filing download, paper-filer identification.
- `src/verify_donor_data.py` — patterns for the mapping audit.
- `src/provenance.py` — used by every briefing for source/confidence metadata.

## Sequencing

Two streams, parallel. Stream 1 unblocks accurate totals. Stream 2 unblocks the briefing.

**Stream 1 (evidence base):** F497 re-enable (~30 min) → manual Anderson refresh (operator, parallel) → paper extractor (~half day) → mapping audit.

**Stream 2 (briefing):** Migrations 098/099 → generator skeleton with F1–F4 → candidate-page sections (D1, unblocked) → F5/F6/F7/F8/F9 → dashboard page (D2) → existing scanner Tier integration (last, doesn't block).

## Verification

**Article-as-oracle harness** (the headline test). `tests/test_filing_period_briefing.py` runs the generator against a Q1 2026 contributions snapshot and asserts the rendered briefing names the same candidates and surfaces the same observations as the Richmondside article. This becomes the regression test that runs every filing period in every city forever. Failing this test = briefing spec is wrong.

**Data layer:**
- `python src/data_sync.py netfile --sync-type full` populates types 20/21.
- `python src/netfile_paper_extractor.py --filer anderson_mayor_2026` produces JSON matching schema; idempotent.
- Anderson candidate page total reconciles to ~$40,500 (per article).
- `mcp__netfile__search_contributions` cross-check matches our `contributions` rows for same period.
- `python src/audit_committee_mapping.py` reports zero orphans for 2026 races.

**Briefing layer:**
- `python src/filing_period_briefing.py --period 2026-Q1` produces a structured briefing with all sections populated.
- `pytest tests/test_filing_period_briefing.py` passes.
- `pytest tests/test_pipeline_manifest.py::TestLivenessExpectations` covers new liveness checks (F497 records present in last 30 days; paper-filer freshness < 14 days during election season).

**Display layer:**
- `cd web && npm run dev`. Visit candidate pages for Anderson, Jimenez, Pursell, Robinson, Johnson, Martinez. Totals, top donors, geography reconcile to article.
- Visit `/elections/.../finance`. Cross-candidate comparison renders; numbers reconcile.
- `tests/test_anon_visibility.py` covers any new public table.

**Framing review (judgment call, operator):**
- F5 cross-candidate clustering copy.
- F9 Levine-on-contribution-side labels (legal weight per `financial-disclosure-framing.md`).
- Initial briefing publication tier — proposed Graduated (new feature category, AI-generated narrative).

## Open items

- Confirm Levine Act contract-value floor for F9 (Gov. Code §84308 — currently $500 contribution side; contract side spec needs cite check).
- Confirm zip-prefix bucketing for F2 matches operator's Richmond-vs-Bay-Area mental model (94801–94808 = Richmond proper).
- Confirm briefing publication tier proposal: **Graduated** (start operator-only, promote per-section after Q1 review). The briefing as a *category* is new and AI-generated; per `team-operations.md` rubric, Graduated is the default.
