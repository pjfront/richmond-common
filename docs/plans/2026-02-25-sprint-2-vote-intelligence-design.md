# Sprint 2 Design: Vote Intelligence

**Date:** 2026-02-25
**Status:** Approved
**Sprint items:** S2.1 (Vote Categorization), S2.2 (Category Display), S2.3 (AI-Generated Bios)
**Next step:** Implementation plan (writing-plans skill, next session)

---

## Context

Sprint 2 is the "Vote Intelligence" sprint. It builds on Sprint 1's data foundation (23 meetings, 533 agenda items, 102 motions, 699 votes, 7 officials) to add categorization refinement, richer display surfaces, and AI-generated council member profiles.

Key discovery during design: the extraction pipeline already categorizes 100% of agenda items. Sprint 2 refines the taxonomy, exposes categories on more surfaces, and adds biographical intelligence.

---

## S2.1: Vote Categorization Taxonomy

**Priority:** Paths A+B+C | **Publication tier:** Public

### Current State

- 12-category `AgendaCategory` enum in `src/models.py`
- `category VARCHAR(50)` column on `agenda_items` table, 100% populated
- Extraction prompt in `src/extraction.py` already assigns categories
- Frontend `CategoryBadge` component renders categories with color coding

### Category Distribution (as of design)

| Category | Count | Notes |
|----------|-------|-------|
| contracts | 130 | Accurately tagged |
| governance | 95 | 30 are appointment items |
| other | 66 | Genuinely procedural (pledge, closed session reports) |
| infrastructure | 65 | |
| personnel | 50 | 28 are appointment items |
| public_safety | 39 | |
| budget | 32 | |
| environment | 20 | |
| housing | 17 | |
| proclamation | 15 | |
| zoning | 4 | |
| litigation | 0 | |

### Changes

**Add `appointments` as 13th category.** Board/commission appointments are currently split between governance (30 items) and personnel (28 items). These are a distinct action type: the council appoints people to boards and commissions. Total: ~58 items to reclassify.

| Change | File | Detail |
|--------|------|--------|
| Add enum value | `src/models.py` | `APPOINTMENTS = "appointments"` |
| Update extraction prompt | `src/extraction.py` | Add "appointments" with description: "board and commission appointments, reappointments, and vacancy actions" |
| Backfill existing data | SQL migration | Reclassify ~58 items matching title keywords (appoint, commission, board, vacancy, reappoint). Human spot-check before committing. |
| Align frontend colors | `web/src/components/CategoryBadge.tsx` | Add `appointments: 'bg-sky-100 text-sky-800'` plus missing backend categories |

**CategoryBadge alignment:** The backend enum is authoritative. The frontend currently has 14 color mappings that partially overlap with the backend's 12. Resolution:
- Add missing backend values to frontend: `contracts`, `proclamation`, `litigation`, `zoning`, `other`, `appointments`
- Keep forward-looking frontend values (`land_use`, `economic_development`, etc.) as color definitions (zero cost, future-proofing)
- Fallback `bg-slate-100 text-slate-600` handles any unmapped value

---

## S2.2: Category Display Surfaces

**Priority:** Path A | **Publication tier:** Graduated

### Already Working

- **Meeting detail** (`/meetings/[id]`): `AgendaItemCard` shows `CategoryBadge` per item
- **Council profile** (`/council/[slug]`): `VotingRecordTable` has category column

### New Surfaces

| Surface | What to show | Complexity |
|---------|-------------|------------|
| **Meetings list** (`/meetings`) | Category summary chips below each meeting (top 3-4 categories with item counts) | Medium. Aggregate query or client-side rollup. |
| **Council profile stats** | Category breakdown (stat cards or chart showing what topics a member votes on most) | Medium. Query votes joined to agenda_items grouped by category. |
| **Transparency reports** (`/reports/[slug]`) | Category badge on conflict flag cards | Low. `getConflictFlagsDetailed()` needs to SELECT category from its existing agenda_items join. |

### Not In Scope

Category-based filtering, category landing pages, cross-member comparison. Those are S6 (Pattern Detection) dependencies.

---

## S2.3: AI-Generated Council Member Bios

**Priority:** Paths A+B+C | **Publication tiers:** Layer 1 Public, Layer 2 Graduated

### Design Principle

Two-layer structure with transparent AI construction. Layer 1 is pure data aggregation (no AI judgment). Layer 2 is AI-synthesized narrative with explicit disclosure of how it was built.

### Layer 1: Factual Profile (Public)

Derived directly from database queries. No AI inference. No editorial judgment.

| Field | Source | Example |
|-------|--------|---------|
| Name, role, seat | `officials` table | "Councilmember, District 1" |
| Term dates | `officials` table | "Serving since Jan 2023" |
| Meeting attendance rate | `votes` count vs. `meetings` count | "Attended 22 of 24 meetings (92%)" |
| Total votes cast | `votes` table | "Cast 487 votes across 22 meetings" |
| Top categories by vote count | `votes` + `agenda_items` | "Most active in: Contracts (98), Governance (72)" |
| Voting alignment rate | `votes` table | "Voted with majority 89% of the time" |

### Layer 2: AI-Synthesized Summary (Graduated)

Claude generates a short narrative (2-3 sentences) from the factual data, with mandatory transparency disclosure.

**Template:**

```
[AI-generated summary paragraph]

---
This summary was generated by AI based on [member]'s voting record
across [N] meetings. It reflects patterns in official vote data,
not editorial judgment.
Data sources: City of Richmond certified meeting minutes
Last updated: [date]
```

**Constraints on AI summary generation:**
- States what the data shows. Does not interpret why.
- Does not characterize political orientation or ideology.
- Does not compare members to each other.
- Does not use value-laden language (good/bad, strong/weak).

**Example output:**

> "Councilmember Martinez has participated in 22 of 24 regular meetings since January 2023, casting 487 votes. Their voting record shows particular activity in contracts and governance items, with consistent majority alignment at 89%. They have been the sole dissenting vote on 12 occasions, most frequently on budget and infrastructure items."

### Implementation

- Bio generation is a pipeline task (`src/bio_generator.py`), not client-side
- Store in `officials` table: `bio_factual JSONB`, `bio_summary TEXT`, `bio_generated_at TIMESTAMPTZ`, `bio_model VARCHAR(50)`
- Regenerate on each pipeline run when vote data changes
- Include generation metadata for auditability
- Frontend renders Layer 1 always; Layer 2 behind operator gate until approved per member

---

## Cross-Cutting Concerns

### Database Changes

| Table | Change | Type |
|-------|--------|------|
| `agenda_items` | Backfill ~58 rows: category to 'appointments' | Data migration |
| `officials` | Add `bio_factual`, `bio_summary`, `bio_generated_at`, `bio_model` columns | DDL migration |

### Testing Strategy

- **Pipeline:** Test bio generation with mock vote data. Test appointment reclassification logic.
- **Frontend:** Test CategoryBadge renders all 13+ categories. Test new display surfaces with fixture data.
- **Integration:** Spot-check bio output against known council members.

### Explicitly Out of Scope

- Category-based search/filtering (S6)
- Coalition analysis (S6)
- Cross-member comparison charts (S6)
- Public comment generation (deferred per project spec)
- Form 700 integration (S5)

---

## Decision Log

| Decision | Rationale |
|----------|-----------|
| Add 'appointments' as 13th category | 58 items split between governance/personnel are a distinct action type. Clean separation improves downstream analysis. |
| Two-layer bio structure | Separates factual aggregation (safe to publish) from AI synthesis (needs review). Transparency in AI-generated content is a core project value. |
| Layer 2 bios are Graduated tier | AI-generated narrative about elected officials carries reputation risk. Operator reviews before public exposure. |
| Keep forward-looking CategoryBadge colors | Zero-cost future-proofing. Frontend gracefully handles any category value. |
| Store bios in officials table, not generated on-the-fly | Auditability (generation metadata), performance (no API call per page load), consistency (same bio until data changes). |
