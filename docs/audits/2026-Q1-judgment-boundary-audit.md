# Judgment-Boundary Audit: Q1 2026

**Date:** 2026-03-07
**Auditor:** Claude (AI-delegable per S7.3 spec)
**Scope:** All decision points in pipeline (`src/`) and frontend (`web/`)
**Methodology:** Systematic inventory of all `if` branches, thresholds, configuration choices, and process decisions that affect system behavior. Each decision point assessed for correct delegation.

---

## Executive Summary

**69 decision points inventoried.** 61 (88%) are correctly delegated. The system's judgment boundary is well-calibrated.

| Category | Finding |
|---|---|
| Should remain judgment calls | 9/9 current judgment calls are correctly classified |
| Should become judgment calls | 5 new items identified (framing, thresholds, gate scope) |
| Should become AI-delegable | 2 items currently hardcoded that should use pattern detection |
| Missing from catalog | 3 new decision categories need explicit coverage |
| Cross-cutting concerns | 1 critical threshold synchronization gap |

**Net boundary change:** +5 judgment calls, +2 AI-delegable promotions, +3 new catalog categories.

---

## Direction 1: Judgment Calls Correctly Classified

All 9 items in the current "Judgment Calls (Always Surface)" section remain correctly classified. No demotions recommended.

| Current Judgment Call | Assessment | Reasoning |
|---|---|---|
| Publication tier assignment | Correct | Framing, credibility, city relationship |
| Commit messages changing public view | Correct | Framing sets precedent |
| Content touching city/community | Correct | Personnel Board position, collaborative stance |
| First commit of new feature category | Correct | Framing precedent |
| Strategic decisions with multiple framings | Correct | Weight of choice matters |
| Trust calibration | Correct | Credibility is the project's currency |
| Creative and expressive decisions | Correct | Voice, tone, narrative |
| Values and ethics | Correct | What should vs what can |
| Actions risking credibility | Correct | Existential risk category |

---

## Direction 2: Should Become Judgment Calls (5 new items)

These are currently automated (by omission from the catalog) but carry enough public perception or credibility weight to warrant human review.

### 2.1 Public-facing label text changes

**What:** The ConfidenceBadge component uses labels "Potential Conflict," "Financial Connection," and "Low Confidence." These words are the public face of the conflict detection system.

**Where:** `web/src/components/ConfidenceBadge.tsx:2-16`

**Why flag:** These labels directly shape public perception of what the system does. "Potential Conflict" vs "Possible Connection" vs "Financial Link" carry different implications for the city relationship. The initial label choices were made without explicit governance.

**Recommendation:** Changes to public-facing labels and badge colors are judgment calls. Using the existing labels in new contexts is AI-delegable.

### 2.2 Comment generator template framing

**What:** The Jinja template for public comments includes legal framing language ("informational, not legal determination").

**Where:** `src/comment_generator.py` (template)

**Why flag:** This text is sent to the City Clerk on behalf of the project. The framing directly impacts the city relationship and the project's legal posture.

**Recommendation:** Changes to the comment template's framing language are judgment calls. The initial template should be explicitly approved. Routine generation using the approved template is AI-delegable.

### 2.3 AI generation prompt voice/framing changes

**What:** System prompts for summaries, vote explainers, and bios define the voice and framing of AI-generated content.

**Where:** `src/generate_summaries.py`, `src/generate_vote_explainers.py`, `src/generate_bios.py`, `src/plain_language_summarizer.py`

**Why flag:** The catalog correctly identifies "routine pipeline operations" as AI-delegable, including running generators. But modifying the prompts that control the voice and framing of generated content is a creative/expressive decision.

**Recommendation:** Add distinction: *running* generators = AI-delegable. *Modifying generation prompts* that change voice, framing, or editorial stance = judgment call. Modifications for accuracy, completeness, or bug fixes = AI-delegable.

### 2.4 OperatorGate scope changes

**What:** Decisions about which pages/features are behind the operator gate vs publicly accessible.

**Where:** `web/src/components/OperatorGate.tsx`, page-level wrapping decisions

**Why flag:** Adding or removing OperatorGate protection is a publication tier decision. Currently not in the catalog.

**Recommendation:** Adding OperatorGate to a page = AI-delegable (conservative direction). Removing OperatorGate from a page = judgment call (graduation decision, equivalent to publication tier change).

### 2.5 Confidence threshold values affecting public visibility

**What:** The specific numeric values (0.6, 0.7, 0.5, 0.4) that determine whether a conflict flag is displayed publicly as Tier 1, Tier 2, or suppressed.

**Where:** `src/conflict_scanner.py:1033-1038`, `web/src/components/ConfidenceBadge.tsx:2-16`, `web/src/app/reports/[meetingId]/page.tsx:44-46`

**Why flag:** These thresholds directly control what citizens see. The mechanism (confidence-based tier assignment) is AI-delegable. But the specific boundary values determine the false positive/negative tradeoff for the public, and getting that wrong damages credibility.

**Recommendation:** The threshold mechanism is AI-delegable. Changes to the specific threshold values are judgment calls requiring review of the impact on currently-flagged items.

---

## Direction 3: Should Become AI-Delegable (2 promotions)

### 3.1 Hardcoded council member fallback lists

**What:** `src/conflict_scanner.py:128-137` contains hardcoded lists of current and former council members as a fallback when the database is empty.

**Current state:** Manually maintained hardcoded lists.

**Recommendation:** Promote to AI-delegable with auto-detection. The system should compare the `city_config` registry and the `officials` database table against these fallback lists and flag staleness. When lists diverge, auto-update the fallback or (better) eliminate it by requiring the database to be populated first.

### 3.2 Comment compilation detection by ADID enumeration

**What:** `src/batch_extract.py:86` uses `KNOWN_COMMENT_COMPILATION_ADIDS = {"17313", "17289", "17274", "17234"}` to identify comment compilations.

**Current state:** Hardcoded set of 4 known document IDs.

**Recommendation:** Promote to AI-delegable with pattern detection. Replace exhaustive enumeration with content-based detection (title matching for "public comment," document metadata analysis, or structural analysis of document content). Hardcoded ID enumeration will silently fail on every future meeting.

---

## Direction 4: Missing Catalog Categories (3 new)

### 4.1 Threshold synchronization

The catalog covers individual decisions but not the meta-decision of keeping related values synchronized across layers. When the conflict scanner assigns Tier 1 at confidence >= 0.6 but the frontend displays "Potential Conflict" only at >= 0.7, that gap is unintentional but undetected.

**Recommendation:** Add to AI-delegable: "Maintaining synchronization between backend tier assignment thresholds and frontend display thresholds. When a threshold is changed in one location, propagate to all related locations and flag if the change affects public visibility (which then becomes a judgment call per 2.5)."

### 4.2 Prompt operations vs prompt modifications

The catalog says "routine pipeline operations" are AI-delegable, which is correct for running generators. But the catalog doesn't distinguish between running a prompt and modifying a prompt. This gap has been covered by 2.3 above.

### 4.3 Database migration scope

The catalog doesn't address database migrations. These are currently run manually in Supabase SQL Editor (correctly), but the decision about what goes into a migration is implicit.

**Recommendation:** Add to AI-delegable: "Writing and proposing database migrations. Migrations follow established patterns (idempotent, `IF NOT EXISTS`). Running migrations in production remains a human action (Supabase SQL Editor)."

---

## Cross-Cutting Concern: Threshold Synchronization Gap

**Priority: HIGH. This is the single most architecturally important finding.**

The confidence-to-tier mapping is defined in four separate locations:

| Location | Tier 1 Boundary | Tier 2 Boundary | Tier 3 |
|---|---|---|---|
| `conflict_scanner.py:1033-1038` | sitting + >= 0.6 | sitting + >= 0.4 | else |
| `reports/[meetingId]/page.tsx:44-46` | >= 0.7 | >= 0.5 and < 0.7 | not shown |
| `ConfidenceBadge.tsx:2-16` | >= 0.7 | >= 0.5 | < 0.5 |
| `queries.ts:542` | (n/a) | >= 0.5 (published count) | < 0.5 |

**The gap:** A conflict flag with confidence 0.65 is stored as `publication_tier = 1` in the database but rendered as "Financial Connection" (amber, Tier 2 styling) on the frontend. The `publication_tier` column is effectively decorative on the frontend path.

**Impact assessment:** The frontend's defense-in-depth approach (re-deriving tiers from raw confidence) is actually good engineering. But:
- The comment generator uses `publication_tier` from the database, so a comment might reference a "potential conflict" that the website displays as a "financial connection"
- The gap between 0.6 and 0.7 means some findings the scanner considers highest-tier are visually downgraded for citizens

**Resolution options (judgment call for operator):**

| Option | Change | Effect |
|---|---|---|
| A: Align frontend down | Change ConfidenceBadge to >= 0.6 / >= 0.4 | More findings shown as "Potential Conflict." More aggressive. |
| B: Align scanner up | Change scanner to >= 0.7 / >= 0.5 | Fewer Tier 1 flags. More conservative. |
| C: Single source of truth | Create shared threshold config used by both | No immediate behavior change, but eliminates future drift. Combined with A or B. |
| D: Document the gap | Treat frontend thresholds as the "publication" boundary and scanner tiers as the "analysis" boundary | Codifies current behavior. The gap becomes intentional (scanner casts a wider net, frontend filters conservatively). |

**Recommendation:** Option D + C. Document that the scanner intentionally assigns tiers more aggressively than the frontend displays. Create a shared threshold config to prevent future unintentional drift. This preserves defense-in-depth while making the design explicit.

---

## Pending Judgment Calls

These require operator decision. Each is a decision packet.

### JC-1: Confirm publication tier for 3 ungated pages

Three pages are publicly accessible without OperatorGate:

| Page | Route | Content | Risk |
|---|---|---|---|
| Data Quality | `/data-quality` | Freshness, completeness, anomaly dashboard | Low (operational metrics, no inference) |
| Coalitions | `/council/coalitions` | Pairwise voting alignment, bloc detection | Medium (political framing, coalition labels) |
| Patterns | `/council/patterns` | Donor-category cross-meeting patterns | Medium (implies connections between donations and votes) |

**Question:** Were these explicitly graduated to public, or did they ship public without a tier review?

- If graduated: no action needed, but log the decision
- If not reviewed: each needs a publication tier judgment call

### JC-2: Threshold synchronization resolution

See cross-cutting concern above. Which option (A/B/C/D)?

### JC-3: Comment template initial approval

Has the comment generator's template framing ("informational, not legal determination") been explicitly approved as the project's voice for city communications? If yes, log it. If no, review the template.

---

## Audit Process (for quarterly recurrence)

### Inputs
1. Current `judgment-boundaries.md`
2. Git log since last audit (new files, new decision points)
3. Session history: cases of over-prompting (AI asked when it should have decided) and under-prompting (AI decided when it should have asked)

### Steps
1. **Inventory new decision points** from code changes since last audit
2. **Review each current judgment call:** Still requires human input? Evidence of over-prompting?
3. **Review each AI-delegable category:** Any incidents of under-prompting? New risk factors?
4. **Check threshold synchronization:** All related values aligned across layers?
5. **Check catalog coverage:** Any decision types not represented?
6. **Produce findings:** Proposed boundary changes, pending judgment calls, cross-cutting concerns

### Outputs
1. Audit report (this document format)
2. Proposed `judgment-boundaries.md` changes
3. Decision packets for pending judgment calls
4. Updated threshold inventory

### Cadence
- **Quarterly** audit (per S7.3 spec)
- **Ad hoc** when a new feature category introduces a new decision type
- **Boundary Review section** of the catalog captures between-audit observations

---

## Appendix: Full Decision Point Inventory

### By Assessment Category

**Correctly Delegated (61):**
- 11 conflict scanner confidence decisions
- 3 temporal correlation decisions
- 2/3 name matching decisions
- 2 bias audit decisions
- 1 text quality decision
- 4 cloud pipeline safety controls
- 2/3 comment generator decisions
- 3/4 content generation decisions
- 3 Form 700 extractor decisions
- 3 contribution enricher decisions
- 6 extraction schema decisions
- 5/6 scraper decisions
- 3 monitoring decisions
- 3 decision queue/self-assessment decisions
- 1 hierarchy classifier decision
- 2/3 frontend operator gate decisions
- 2/4 frontend display decisions
- 3 data sync/config decisions
- 3 process-level decisions

**Should Promote to AI-Delegable (2):**
- Hardcoded council member fallback lists → auto-detection
- Comment compilation ADID enumeration → pattern detection

**Should Flag as Judgment Call (5):**
- Public-facing label text changes (ConfidenceBadge)
- Comment generator template framing
- AI generation prompt voice/framing changes
- OperatorGate scope changes (removal only)
- Confidence threshold value changes affecting public visibility

**Pending Judgment Calls (3):**
- JC-1: Publication tier confirmation for 3 ungated pages
- JC-2: Threshold synchronization resolution
- JC-3: Comment template initial approval
