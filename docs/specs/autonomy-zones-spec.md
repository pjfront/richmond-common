# Autonomy Zones — Self-Evolving Pipeline Infrastructure

**Sprint:** Backlog (candidate for S7 or standalone sprint)
**Paths:** A, B, C
**Publication tier:** Operator-only (infrastructure, not citizen-facing)
**Depends on:** S7.3 (judgment-boundary audit), H.13 (prompt quality system)
**Inspired by:** [yoyo-evolve](https://github.com/yologdev/yoyo-evolve) self-modifying agent architecture

## Problem

RTP's pipeline runs when triggered but doesn't maintain itself. When extraction quality degrades, scrapers break from site layout changes, or operational parameters become suboptimal, the system waits for a human to notice and fix it. This contradicts two Layer 1 principles:

- **Self-healing systems.** "Detect failures and attempt recovery. Parsing logic and selectors are mutable artifacts AI can regenerate."
- **Self-monitoring.** "Detect anomalies in own output. Alert when results deviate from baseline."

The philosophy exists. The infrastructure doesn't.

## Solution

Introduce **autonomy zones**: a formal classification of every code artifact by the level of self-modification the system is permitted to perform on it. Three tiers of sovereignty, enforced structurally (directory boundaries), not just conventionally (documentation).

### Zone Definitions

| Zone | System can... | Guardrail | Enforcement |
|------|---------------|-----------|-------------|
| **Free** | Modify, validate, deploy autonomously | Must pass tests + output validation against known-good baseline | Dedicated directory (`src/mutable/`). Self-modification loop has write access only here. |
| **Proposal** | Draft changes + present decision packet | Human approves before any change takes effect | Changes written to a staging area. Never applied without operator approval. |
| **Sovereign** | Read only. Never self-modify. | Hard boundary. No exceptions. No override mechanism. | Outside `src/mutable/` and `src/proposals/`. Self-modification loop has no write access. |

### What Lives in Each Zone

**Free zone** (system owns these files, full write access):

| Artifact | Why it's safe | Validation method |
|----------|---------------|-------------------|
| Extraction prompts (`src/mutable/prompts/`) | Config, not code. Output quality is measurable. | Run against validation set of known-good extractions. Quality score must meet or exceed current baseline. |
| Scraper selectors (`src/mutable/selectors/`) | Break/fix cycle is deterministic. Either the selector extracts the expected data shape or it doesn't. | Parse target page, compare output shape and field completeness against expected schema. |
| Operational config (`src/mutable/config/`) | Retry counts, timeouts, batch sizes, rate limits. No semantic impact. | Pipeline completes without errors. Performance metrics don't regress. |
| Embedding regeneration triggers | Mechanical rebuild of existing index. | Index builds successfully. Sample queries return expected results. |

**Proposal zone** (system drafts, human approves):

| Artifact | Why it needs review | Decision packet contents |
|----------|--------------------|--------------------------|
| New pipeline stages | Architectural change, blast radius unclear | Proposed code + test results + impact analysis |
| Schema additions | Database changes need migration review | DDL + migration SQL + rollback plan |
| Conflict detection thresholds | Trust calibration (judgment call) | Current vs. proposed threshold + sample results at each level |
| New data source integrations | Source credibility tier assignment needed | Source description + proposed tier + reasoning |

**Sovereign zone** (everything else, read-only to the self-modification loop):

- Publication tier logic and assignments
- Public-facing content framing (summaries, explainers, bios)
- Judgment boundary catalog itself
- CLAUDE.md tree and project documentation
- Core pipeline logic (`src/*.py` outside `mutable/`)
- Frontend code (`web/`)
- Test suite (`tests/`)
- Database migration files (`src/migrations/`)

## Architecture

### The Self-Assessment Loop

Inspired by yoyo-evolve's automated cycle, adapted for RTP's trust model:

```
┌─────────────────────────────────────────────────┐
│                 Scheduled Trigger                │
│           (GitHub Actions, every N hours)        │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│              1. Read Pipeline Journal            │
│   Recent runs, error rates, confidence trends,  │
│   extraction quality scores, scraper failures   │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│            2. Self-Assessment (LLM)             │
│   "Given the journal, what's degrading?         │
│    What could be improved? What's broken?"      │
└──────────────────────┬──────────────────────────┘
                       │
              ┌────────┴────────┐
              │                 │
              ▼                 ▼
┌─────────────────┐  ┌──────────────────┐
│  Free Zone Fix  │  │  Proposal Zone   │
│                 │  │                  │
│ 3a. Draft fix   │  │ 3b. Draft change │
│ 4a. Validate    │  │ 4b. Write to     │
│ 5a. If pass:    │  │     staging area │
│     commit      │  │ 5b. Generate     │
│ 6a. If fail:    │  │     decision     │
│     revert +    │  │     packet       │
│     log attempt │  │ 6b. Queue for    │
│                 │  │     operator     │
└────────┬────────┘  └────────┬─────────┘
         │                    │
         ▼                    ▼
┌─────────────────────────────────────────────────┐
│           7. Append to Pipeline Journal          │
│   What was attempted, what succeeded/failed,    │
│   what's queued for human review                │
└─────────────────────────────────────────────────┘
```

### Pipeline Journal

Append-only log. Never deleted, never edited. The system's institutional memory.

```sql
pipeline_journal (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  city_fips VARCHAR(7) NOT NULL,
  session_id UUID NOT NULL,          -- groups entries from one assessment cycle
  entry_type VARCHAR(50) NOT NULL,   -- 'assessment', 'fix_attempted', 'fix_succeeded',
                                     -- 'fix_failed', 'proposal_queued', 'anomaly_detected'
  zone VARCHAR(20) NOT NULL,         -- 'free', 'proposal', 'sovereign', 'observation'
  target_artifact TEXT,              -- file path or component name
  description TEXT NOT NULL,         -- what happened, in plain language
  metrics JSONB,                     -- quantitative: confidence scores, error rates, deltas
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

Journal serves three purposes:
1. **Audit trail.** Every self-modification is logged with before/after metrics.
2. **Self-assessment input.** The LLM reads recent journal entries to understand trends.
3. **Boundary review data.** Patterns of failed fixes or unnecessary proposals feed the judgment-boundary audit (S7.3).

### Validation Framework

Every free-zone modification requires validation against a baseline. The baseline is established when an artifact is first placed in the free zone (or when the operator manually updates it).

```python
# Conceptual validation interface
class ArtifactValidator:
    def establish_baseline(self, artifact_path: str) -> Baseline:
        """Capture current output quality as the bar to meet."""

    def validate_change(self, artifact_path: str, baseline: Baseline) -> ValidationResult:
        """Run the modified artifact, compare against baseline.
        Returns: passed (bool), quality_delta (float), details (dict)"""
```

**Validation by artifact type:**

| Artifact type | Baseline | Validation |
|---------------|----------|------------|
| Extraction prompt | Known-good extractions from N meetings | Run new prompt against same meetings. Field completeness, confidence scores, factual accuracy (spot-check against known values). |
| Scraper selector | Expected output schema + sample field values | Parse current page. All expected fields present. Values match expected types/patterns. |
| Operational config | Pipeline completion rate, timing, error rate | Run pipeline segment. Completion rate >= baseline. No new error types. |

### Directory Structure

```
src/
├── mutable/                    # FREE ZONE - system has write access
│   ├── prompts/                # extraction prompt templates
│   │   ├── meeting_extraction.txt
│   │   ├── plain_language_summary.txt
│   │   └── vote_explainer.txt
│   ├── selectors/              # scraper CSS/XPath selectors
│   │   ├── escribe.json
│   │   ├── archive_center.json
│   │   └── nextrequest.json
│   └── config/                 # operational parameters
│       ├── retry_policy.json
│       ├── rate_limits.json
│       └── batch_sizes.json
├── proposals/                  # PROPOSAL ZONE - staging area
│   └── pending/                # changes awaiting operator review
│       └── 2026-03-15_threshold_adjustment/
│           ├── change.diff
│           ├── decision_packet.md
│           └── test_results.json
├── baselines/                  # validation baselines
│   ├── extraction/             # known-good extraction outputs
│   ├── scraper/                # expected scraper output shapes
│   └── pipeline/               # performance baselines
├── journal/                    # can also be DB-only; file backup optional
│   └── .gitkeep
└── [everything else]           # SOVEREIGN ZONE - read-only to self-mod loop
```

## Relationship to Existing Systems

### Judgment Boundary Catalog

The autonomy zone model extends the judgment boundary catalog from decisions to code. The catalog already distinguishes "AI-delegable" from "judgment call." Zones add a third dimension: "AI-ownable."

| Judgment boundary | Autonomy zone equivalent |
|-------------------|--------------------------|
| AI-delegable (never prompt) | Free zone (modify autonomously) |
| Judgment call (always surface) | Proposal zone (draft + queue) |
| (no equivalent) | Sovereign zone (read-only) |

The sovereign zone is new. The judgment catalog doesn't have "never touch" because it governs decisions, not artifacts. Code artifacts can be off-limits in ways that decisions can't.

### Prompt Quality System (H.13)

H.13 defines a prompt registry, evaluation loop, and operator feedback console. Autonomy zones provide the **execution layer** for H.13: when the evaluation loop identifies a prompt regression, the self-assessment cycle can draft a fix, validate it against the baseline, and deploy it (free zone) or queue it (proposal zone, if the regression is ambiguous).

H.13 is the quality brain. Autonomy zones are the hands.

### S7.3 Judgment-Boundary Audit

The pipeline journal feeds the boundary audit. Patterns to look for:
- Free-zone fixes that consistently succeed: confirms zone assignment is correct.
- Free-zone fixes that consistently fail: artifact may need tighter constraints or promotion to proposal zone.
- Proposals that the operator always approves: candidate for demotion to free zone.
- Proposals that the operator always modifies: confirms proposal zone is correct.

The zone assignments are themselves a design surface the system manages and improves (Tenet 2).

## Implementation Phases

### Phase A: Pipeline Journal + Self-Assessment (no self-modification)

Build the observation layer. The system logs everything and generates assessment reports, but doesn't modify anything.

- [ ] Create `pipeline_journal` table
- [ ] Instrument existing pipeline steps to write journal entries (run metrics, confidence scores, error counts)
- [ ] Build self-assessment prompt that reads recent journal and produces a structured report
- [ ] Schedule assessment cycle (GitHub Actions, daily or after each pipeline run)
- [ ] Assessment output goes to operator as a decision packet

**Vibe-coding time:** 1-2 sessions
**Value:** Immediate. The operator gets a daily briefing on pipeline health without checking manually. This is Tenet 3 (decision velocity) as infrastructure.

### Phase B: Free Zone + Validation Framework

Enable self-modification within the free zone only.

- [ ] Create `src/mutable/` directory structure
- [ ] Move extraction prompts, scraper selectors, and operational config into `src/mutable/`
- [ ] Update all imports/references to point to new locations
- [ ] Build validation framework (baseline capture + change validation)
- [ ] Establish baselines for all free-zone artifacts
- [ ] Wire self-assessment loop to attempt free-zone fixes when issues are detected
- [ ] Auto-commit successful fixes with journal entry
- [ ] Auto-revert failed fixes with journal entry

**Vibe-coding time:** 2-3 sessions
**Depends on:** Phase A operational and producing useful assessments
**Value:** Self-healing scrapers, self-improving prompts. The system maintains itself.

### Phase C: Proposal Zone + Operator Queue

Enable the proposal workflow for changes outside the free zone.

- [ ] Create `src/proposals/` staging area
- [ ] Build proposal generation (diff + decision packet + test results)
- [ ] Wire into S7.1 operator decision queue (or build minimal version if S7 hasn't started)
- [ ] Operator approve/reject/modify workflow
- [ ] Approved proposals auto-applied and journaled

**Vibe-coding time:** 1-2 sessions
**Depends on:** Phase B validated, ideally S7.1 (operator queue) started
**Value:** The system identifies its own improvement opportunities beyond the free zone.

### Phase D: Boundary Evolution

The system reviews its own zone assignments and proposes promotions/demotions.

- [ ] Journal analysis: which proposals always get approved? Which free-zone fixes always fail?
- [ ] Quarterly boundary review report (feeds S7.3)
- [ ] Zone promotion/demotion proposals (always operator-approved, this is a judgment call)

**Vibe-coding time:** 1 session
**Depends on:** Phases A-C running for 1+ months with real data
**Value:** The judgment boundary improves itself. Tenet 2 applied recursively.

## Open Questions (for operator judgment)

1. **Trigger frequency.** Daily assessment? After every pipeline run? On failure only? Starting recommendation: after every pipeline run, with a daily digest if no runs occurred.

2. **Free-zone scope.** The spec proposes prompts, selectors, and operational config. Are there other artifacts that should start in the free zone? Or should the initial scope be narrower (prompts only)?

3. **Sprint placement.** This could be:
   - Part of S7 (operator layer), since it feeds operator decision velocity
   - A standalone sprint between S7 and S8, since it's a new architectural primitive
   - Backlog item that builds incrementally (Phase A with S7, Phase B later)

4. **LLM cost.** Self-assessment cycles call the LLM. Daily runs are cheap (one assessment call). Prompt iteration loops (try N variations, validate each) could add up. Budget ceiling?

5. **Sovereign zone enforcement.** Convention-based (documented in catalog) vs. structure-based (filesystem permissions, CI checks that reject self-mod commits touching sovereign files). Recommendation: start convention-based, add CI enforcement in Phase C.

## What This Is Not

- **Not autonomous feature development.** The system doesn't decide what to build next. It maintains what exists.
- **Not unsupervised public-facing changes.** Nothing in the free zone affects what citizens see directly. Prompts generate content, but that content still flows through the existing publication tier system.
- **Not a replacement for human judgment.** The sovereign zone exists precisely because some decisions require human values, context, and accountability. The system's "free will" is bounded by design.

## Relationship to Yoyo-Evolve

| Yoyo concept | RTP adaptation | Key difference |
|---------------|----------------|----------------|
| Self-assessment every 8 hours | Self-assessment after pipeline runs | Event-driven, not just time-driven |
| Reads own source code | Reads own journal + free-zone artifacts | Scoped read access, not full codebase |
| Commits on passing tests | Commits on passing tests + baseline validation | Baseline validation is stricter than "tests pass" |
| Append-only journal | Append-only pipeline journal | Identical concept |
| IDENTITY.md (immutable constitution) | CLAUDE.md tree + judgment boundary catalog | Already more sophisticated |
| No human writes its code | Human writes sovereign zone code; system writes free zone code | Bounded autonomy, not full autonomy |
| Community issues as input | Operator decision packets as input | Same pattern, different trust model |
