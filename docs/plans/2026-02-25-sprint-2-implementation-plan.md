# Sprint 2: Vote Intelligence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add vote categorization refinement, category display on three new surfaces, and AI-generated council member bios with a two-layer public/graduated structure.

**Architecture:** Backend-first approach. Pipeline changes (enum, extraction schema, backfill) come first, then DB migration for bio columns, then frontend display surfaces, then bio generation. Each layer builds on the last. TDD throughout.

**Tech Stack:** Python 3 (pipeline), PostgreSQL/Supabase (DB), Next.js 16 + React 19 + TypeScript (frontend), Claude API (bio generation)

**Vibe-coding time estimate:** ~3-4 hours across tasks

**Design doc:** `docs/plans/2026-02-25-sprint-2-vote-intelligence-design.md`

---

## Task 1: Add `appointments` to AgendaCategory Enum

**Files:**
- Modify: `src/models.py:32-44`
- Test: `tests/test_models_category.py` (create)

**Step 1: Write the failing test**

Create `tests/test_models_category.py`:

```python
"""Tests for AgendaCategory enum completeness."""
from src.models import AgendaCategory


def test_appointments_category_exists():
    """The appointments category must exist in the enum."""
    assert AgendaCategory.APPOINTMENTS == "appointments"


def test_all_expected_categories_present():
    """All 13 categories must be present."""
    expected = {
        "zoning", "budget", "housing", "public_safety",
        "environment", "infrastructure", "personnel",
        "contracts", "governance", "proclamation",
        "litigation", "other", "appointments",
    }
    actual = {c.value for c in AgendaCategory}
    assert actual == expected
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_models_category.py -v`
Expected: FAIL with `AttributeError: APPOINTMENTS`

**Step 3: Add `APPOINTMENTS` to enum**

In `src/models.py`, add after `OTHER = "other"` (line 44):

```python
    APPOINTMENTS = "appointments"
```

The full enum should now have 13 values.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_models_category.py -v`
Expected: 2 passed

**Step 5: Commit**

```bash
git add src/models.py tests/test_models_category.py
git commit -m "feat: add appointments as 13th agenda category"
```

---

## Task 2: Update Extraction Schema with `appointments`

The extraction schema in `src/extraction.py` defines the JSON schema sent to Claude for meeting minutes extraction. The category enum appears in TWO places with inconsistent constraints. Both need updating.

**Files:**
- Modify: `src/extraction.py:130-137` (consent calendar enum) and `src/extraction.py:159` (action items category)
- Test: `tests/test_extraction_schema.py` (create)

**Step 1: Write the failing test**

Create `tests/test_extraction_schema.py`:

```python
"""Tests for extraction schema category consistency."""
import json
from src.extraction import EXTRACTION_SCHEMA


def _get_consent_category_schema():
    """Navigate to consent_calendar > items > items > properties > category."""
    return (
        EXTRACTION_SCHEMA["properties"]["consent_calendar"]
        ["properties"]["items"]["items"]["properties"]["category"]
    )


def _get_action_category_schema():
    """Navigate to action_items > items > properties > category."""
    return (
        EXTRACTION_SCHEMA["properties"]["action_items"]
        ["items"]["properties"]["category"]
    )


def test_consent_calendar_has_appointments_category():
    schema = _get_consent_category_schema()
    assert "appointments" in schema["enum"]


def test_action_items_has_enum_constraint():
    """Action items category should have an enum constraint, not just type: string."""
    schema = _get_action_category_schema()
    assert "enum" in schema, "action_items category should have an enum constraint"


def test_action_items_has_appointments_category():
    schema = _get_action_category_schema()
    assert "appointments" in schema["enum"]


def test_both_schemas_have_same_categories():
    """Both consent_calendar and action_items should use identical category enums."""
    consent = set(_get_consent_category_schema()["enum"])
    action = set(_get_action_category_schema()["enum"])
    assert consent == action


def test_category_enum_has_13_values():
    """The extraction schema should list all 13 categories."""
    schema = _get_consent_category_schema()
    assert len(schema["enum"]) == 13
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_extraction_schema.py -v`
Expected: Multiple failures (no `appointments`, no enum on action_items)

**Step 3: Update extraction schema**

In `src/extraction.py`, update the consent calendar category enum (lines 130-137) to add `"appointments"`:

```python
                            "category": {
                                "type": "string",
                                "enum": [
                                    "zoning", "budget", "housing", "public_safety",
                                    "environment", "infrastructure", "personnel",
                                    "contracts", "governance", "proclamation",
                                    "litigation", "other", "appointments"
                                ]
                            },
```

And replace the action items category (line 159) from just `{"type": "string"}` to the same enum:

```python
                    "category": {
                        "type": "string",
                        "enum": [
                            "zoning", "budget", "housing", "public_safety",
                            "environment", "infrastructure", "personnel",
                            "contracts", "governance", "proclamation",
                            "litigation", "other", "appointments"
                        ]
                    },
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_extraction_schema.py -v`
Expected: 5 passed

**Step 5: Commit**

```bash
git add src/extraction.py tests/test_extraction_schema.py
git commit -m "feat: add appointments to extraction schema, fix enum consistency"
```

---

## Task 3: Database Migration -- Backfill Appointments + Bio Columns

This single migration handles both S2.1 backfill and S2.3 bio columns. Run manually in Supabase SQL Editor.

**Files:**
- Create: `src/migrations/006_sprint2_vote_intelligence.sql`
- Test: `tests/test_migration_006.py` (create)

**Step 1: Write the migration test**

Create `tests/test_migration_006.py`:

```python
"""Tests for Sprint 2 migration SQL validity."""
import pathlib


MIGRATION_PATH = pathlib.Path(__file__).parent.parent / "src" / "migrations" / "006_sprint2_vote_intelligence.sql"


def test_migration_file_exists():
    assert MIGRATION_PATH.exists()


def test_migration_is_idempotent():
    """Migration should use IF NOT EXISTS and conditional updates."""
    sql = MIGRATION_PATH.read_text()
    # Bio columns use ADD COLUMN IF NOT EXISTS
    assert "IF NOT EXISTS" in sql or "ADD COLUMN IF NOT EXISTS" in sql
    # Backfill uses WHERE to avoid re-classifying
    assert "WHERE" in sql


def test_migration_backfills_appointments():
    """Migration should reclassify items to 'appointments'."""
    sql = MIGRATION_PATH.read_text().lower()
    assert "appointments" in sql
    assert "appoint" in sql  # keyword matching


def test_migration_adds_bio_columns():
    """Migration should add bio_factual, bio_summary, bio_generated_at, bio_model."""
    sql = MIGRATION_PATH.read_text()
    for col in ["bio_factual", "bio_summary", "bio_generated_at", "bio_model"]:
        assert col in sql, f"Missing column: {col}"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_migration_006.py -v`
Expected: FAIL (file does not exist)

**Step 3: Write the migration**

Create `src/migrations/006_sprint2_vote_intelligence.sql`:

```sql
-- Sprint 2: Vote Intelligence
-- S2.1: Backfill ~58 agenda items to 'appointments' category
-- S2.3: Add bio columns to officials table
-- Idempotent: safe to run multiple times

-- ── S2.1: Reclassify appointment items ─────────────────────────

-- Items currently categorized as governance or personnel that are actually
-- board/commission appointments, reappointments, or vacancy actions.
UPDATE agenda_items
SET category = 'appointments'
WHERE category IN ('governance', 'personnel')
  AND (
    title ILIKE '%appoint%'
    OR title ILIKE '%reappoint%'
    OR title ILIKE '%commission%member%'
    OR title ILIKE '%board%member%'
    OR title ILIKE '%vacancy%'
    OR title ILIKE '%board%commission%'
  )
  AND category != 'appointments';

-- ── S2.3: Add bio columns to officials ─────────────────────────

ALTER TABLE officials ADD COLUMN IF NOT EXISTS bio_factual JSONB;
ALTER TABLE officials ADD COLUMN IF NOT EXISTS bio_summary TEXT;
ALTER TABLE officials ADD COLUMN IF NOT EXISTS bio_generated_at TIMESTAMPTZ;
ALTER TABLE officials ADD COLUMN IF NOT EXISTS bio_model VARCHAR(50);

-- Add comment for documentation
COMMENT ON COLUMN officials.bio_factual IS 'Layer 1: factual profile data derived from DB queries (JSON)';
COMMENT ON COLUMN officials.bio_summary IS 'Layer 2: AI-synthesized narrative summary (Graduated tier)';
COMMENT ON COLUMN officials.bio_generated_at IS 'Timestamp of last bio generation';
COMMENT ON COLUMN officials.bio_model IS 'Model used for Layer 2 generation (e.g. claude-sonnet-4-5-20250514)';
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_migration_006.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add src/migrations/006_sprint2_vote_intelligence.sql tests/test_migration_006.py
git commit -m "feat: add migration 006 for appointments backfill and bio columns"
```

**Step 6: Run migration in Supabase**

Manual step: Copy SQL to Supabase SQL Editor and execute. Verify:
- `SELECT category, count(*) FROM agenda_items WHERE category = 'appointments' GROUP BY category;` should show ~58 rows
- `SELECT column_name FROM information_schema.columns WHERE table_name = 'officials' AND column_name LIKE 'bio_%';` should show 4 columns

---

## Task 4: Align CategoryBadge Frontend Colors

The backend has 13 categories (authoritative). The frontend `CategoryBadge` has 14 color mappings that partially overlap. Add missing backend values while keeping forward-looking values.

**Files:**
- Modify: `web/src/components/CategoryBadge.tsx:1-16`

**Step 1: Update color map**

Add the missing backend categories. The full map should be:

```tsx
const categoryColors: Record<string, string> = {
  // ── Backend categories (authoritative) ──
  zoning: 'bg-lime-100 text-lime-800',
  budget: 'bg-green-100 text-green-800',
  housing: 'bg-blue-100 text-blue-800',
  public_safety: 'bg-red-100 text-red-800',
  environment: 'bg-emerald-100 text-emerald-800',
  infrastructure: 'bg-orange-100 text-orange-800',
  personnel: 'bg-pink-100 text-pink-800',
  contracts: 'bg-stone-100 text-stone-800',
  governance: 'bg-purple-100 text-purple-800',
  proclamation: 'bg-violet-100 text-violet-800',
  litigation: 'bg-rose-100 text-rose-800',
  other: 'bg-slate-100 text-slate-600',
  appointments: 'bg-sky-100 text-sky-800',
  // ── Forward-looking (zero-cost future-proofing) ──
  land_use: 'bg-amber-100 text-amber-800',
  economic_development: 'bg-teal-100 text-teal-800',
  health: 'bg-cyan-100 text-cyan-800',
  education: 'bg-indigo-100 text-indigo-800',
  transportation: 'bg-yellow-100 text-yellow-800',
  consent: 'bg-slate-100 text-slate-600',
  ceremonial: 'bg-violet-100 text-violet-800',
}
```

**Step 2: Verify build**

Run: `cd web && npx next build`
Expected: Build succeeds with no errors

**Step 3: Commit**

```bash
git add web/src/components/CategoryBadge.tsx
git commit -m "feat: align CategoryBadge colors with all 13 backend categories"
```

---

## Task 5: Add Category to ConflictFlagCard (Transparency Reports)

The `getConflictFlagsDetailed()` query joins `agenda_items` but only fetches `title` and `item_number`. Add `category` to the select, pass it through to the card, and render a `CategoryBadge`.

**Files:**
- Modify: `web/src/lib/queries.ts:425-440`
- Modify: `web/src/components/ConflictFlagCard.tsx:1-18` (interface) and render section

**Step 1: Update query to fetch category**

In `web/src/lib/queries.ts`, change line 428:

From:
```typescript
    .select('*, agenda_items(title, item_number), officials(name)')
```

To:
```typescript
    .select('*, agenda_items(title, item_number, category), officials(name)')
```

And update the mapping (around line 436) to extract category:

```typescript
  return (data ?? []).map((f) => ({
    ...(f as unknown as ConflictFlag),
    agenda_item_title: (f.agenda_items as { title: string; item_number: string; category: string | null } | null)?.title ?? null,
    agenda_item_number: (f.agenda_items as { title: string; item_number: string; category: string | null } | null)?.item_number ?? null,
    agenda_item_category: (f.agenda_items as { title: string; item_number: string; category: string | null } | null)?.category ?? null,
    official_name: (f.officials as { name: string } | null)?.name ?? null,
  }))
```

**Step 2: Update ConflictFlagCard interface and render**

In `web/src/components/ConflictFlagCard.tsx`, add to the `ConflictFlagDetail` interface (around line 5):

```typescript
  agenda_item_category: string | null
```

Add import at top:
```typescript
import CategoryBadge from './CategoryBadge'
```

Add the badge in the metadata section (after the item title span, around line 49):

```tsx
            {flag.agenda_item_category && (
              <CategoryBadge category={flag.agenda_item_category} />
            )}
```

**Step 3: Verify build**

Run: `cd web && npx next build`
Expected: Build succeeds

**Step 4: Commit**

```bash
git add web/src/lib/queries.ts web/src/components/ConflictFlagCard.tsx
git commit -m "feat: show category badge on conflict flag cards"
```

---

## Task 6: Category Summary Chips on Meetings List

Add category aggregation to `getMeetingsWithCounts()` and display top categories as chips below each meeting card.

**Files:**
- Modify: `web/src/lib/queries.ts:39-93` (add category aggregation)
- Modify: `web/src/lib/types.ts:181-184` (extend `MeetingWithCounts`)
- Modify: `web/src/components/MeetingCard.tsx` (add category chips prop + render)
- Modify: `web/src/app/meetings/page.tsx` (pass category data)

**Step 1: Extend MeetingWithCounts type**

In `web/src/lib/types.ts`, change:

```typescript
export interface MeetingWithCounts extends Meeting {
  agenda_item_count: number
  vote_count: number
}
```

To:

```typescript
export interface CategoryCount {
  category: string
  count: number
}

export interface MeetingWithCounts extends Meeting {
  agenda_item_count: number
  vote_count: number
  top_categories: CategoryCount[]
}
```

**Step 2: Update getMeetingsWithCounts to fetch categories**

In `web/src/lib/queries.ts`, after the existing `itemCounts` query (line 46-49), add a category query. Modify the function to also fetch category data:

After the `itemCounts` fetch (line 49), add:

```typescript
  // Fetch categories per meeting for summary chips
  const { data: itemCategories } = await supabase
    .from('agenda_items')
    .select('meeting_id, category')
    .in('meeting_id', meetingIds)
    .not('category', 'is', null)
```

Before the return statement (line 88), add category aggregation:

```typescript
  // Aggregate categories per meeting (top 4)
  const categoryMap = new Map<string, Map<string, number>>()
  for (const item of itemCategories ?? []) {
    if (!item.category) continue
    if (!categoryMap.has(item.meeting_id)) {
      categoryMap.set(item.meeting_id, new Map())
    }
    const cats = categoryMap.get(item.meeting_id)!
    cats.set(item.category, (cats.get(item.category) ?? 0) + 1)
  }
```

Update the return to include `top_categories`:

```typescript
  return meetings.map((m) => ({
    ...m,
    agenda_item_count: itemCountMap.get(m.id) ?? 0,
    vote_count: voteCountMap.get(m.id) ?? 0,
    top_categories: Array.from(categoryMap.get(m.id)?.entries() ?? [])
      .map(([category, count]) => ({ category, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 4),
  }))
```

**Step 3: Update MeetingCard to accept and render categories**

In `web/src/components/MeetingCard.tsx`, add import and update props:

```typescript
import CategoryBadge from './CategoryBadge'

interface MeetingCardProps {
  id: string
  meetingDate: string
  meetingType: string
  presidingOfficer: string | null
  agendaItemCount: number
  voteCount: number
  topCategories?: { category: string; count: number }[]
}
```

Add the destructured prop and render after the counts div (after line 72):

```tsx
      {topCategories && topCategories.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {topCategories.map((tc) => (
            <span key={tc.category} className="flex items-center gap-1">
              <CategoryBadge category={tc.category} />
              <span className="text-xs text-slate-400">{tc.count}</span>
            </span>
          ))}
        </div>
      )}
```

**Step 4: Update meetings page to pass categories**

In `web/src/app/meetings/page.tsx`, update the `MeetingCard` usage to pass the new prop. Find where `MeetingCard` is rendered and add:

```tsx
topCategories={meeting.top_categories}
```

**Step 5: Verify build**

Run: `cd web && npx next build`
Expected: Build succeeds

**Step 6: Commit**

```bash
git add web/src/lib/types.ts web/src/lib/queries.ts web/src/components/MeetingCard.tsx web/src/app/meetings/page.tsx
git commit -m "feat: show category summary chips on meetings list"
```

---

## Task 7: Category Breakdown on Council Profile

Add a category breakdown section to the council member profile page showing what topics they vote on most.

**Files:**
- Modify: `web/src/lib/queries.ts` (add `getOfficialCategoryBreakdown()` function)
- Create: `web/src/components/CategoryBreakdown.tsx`
- Modify: `web/src/app/council/[slug]/page.tsx` (add breakdown section)

**Step 1: Add query function**

In `web/src/lib/queries.ts`, add after `getOfficialWithStats()` (after line 323):

```typescript
export async function getOfficialCategoryBreakdown(
  officialId: string,
  cityFips = RICHMOND_FIPS
) {
  // Get all votes by this official, joined to agenda items for category
  const { data, error } = await supabase
    .from('votes')
    .select('id, motions!inner(agenda_items!inner(category))')
    .eq('official_id', officialId)

  if (error) throw error

  // Aggregate by category
  const categoryMap = new Map<string, number>()
  for (const vote of data ?? []) {
    const category = (
      (vote as Record<string, unknown>).motions as {
        agenda_items: { category: string | null }
      }
    )?.agenda_items?.category
    if (category) {
      categoryMap.set(category, (categoryMap.get(category) ?? 0) + 1)
    }
  }

  return Array.from(categoryMap.entries())
    .map(([category, count]) => ({ category, count }))
    .sort((a, b) => b.count - a.count)
}
```

**Step 2: Create CategoryBreakdown component**

Create `web/src/components/CategoryBreakdown.tsx`:

```tsx
import CategoryBadge from './CategoryBadge'

interface CategoryBreakdownProps {
  categories: { category: string; count: number }[]
  totalVotes: number
}

export default function CategoryBreakdown({ categories, totalVotes }: CategoryBreakdownProps) {
  if (categories.length === 0) return null

  return (
    <section className="mb-8">
      <h2 className="text-xl font-semibold text-slate-800 mb-3">
        Voting by Topic
      </h2>
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <div className="space-y-3">
          {categories.map((cat) => {
            const pct = totalVotes > 0 ? Math.round((cat.count / totalVotes) * 100) : 0
            return (
              <div key={cat.category} className="flex items-center gap-3">
                <div className="w-28 shrink-0">
                  <CategoryBadge category={cat.category} />
                </div>
                <div className="flex-1">
                  <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-civic-navy rounded-full"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
                <span className="text-sm text-slate-600 w-16 text-right">
                  {cat.count} ({pct}%)
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
```

**Step 3: Wire into council profile page**

In `web/src/app/council/[slug]/page.tsx`:

Add import:
```typescript
import { getOfficialCategoryBreakdown } from '@/lib/queries'
import CategoryBreakdown from '@/components/CategoryBreakdown'
```

Add the query call alongside existing data fetches (in the component's data loading section). Find where `getOfficialWithStats` is called and add:

```typescript
const categoryBreakdown = await getOfficialCategoryBreakdown(official.id)
```

Add the component after the stats bar section (after the closing `)}` of the stats grid, around line 141):

```tsx
      {/* Category Breakdown */}
      <CategoryBreakdown
        categories={categoryBreakdown}
        totalVotes={stats?.vote_count ?? 0}
      />
```

**Step 4: Verify build**

Run: `cd web && npx next build`
Expected: Build succeeds

**Step 5: Commit**

```bash
git add web/src/lib/queries.ts web/src/components/CategoryBreakdown.tsx "web/src/app/council/[slug]/page.tsx"
git commit -m "feat: add category breakdown to council member profiles"
```

---

## Task 8: Update TypeScript Types for Bio Fields

Add bio fields to the `Official` interface so the frontend can render them.

**Files:**
- Modify: `web/src/lib/types.ts:17-31`

**Step 1: Add bio fields to Official interface**

In `web/src/lib/types.ts`, add after `created_at: string` (line 30):

```typescript
  bio_factual: Record<string, unknown> | null
  bio_summary: string | null
  bio_generated_at: string | null
  bio_model: string | null
```

**Step 2: Verify build**

Run: `cd web && npx next build`
Expected: Build succeeds (existing code uses `select('*')` so new nullable fields won't break)

**Step 3: Commit**

```bash
git add web/src/lib/types.ts
git commit -m "feat: add bio fields to Official TypeScript interface"
```

---

## Task 9: Bio Generator Pipeline Module

Create the pipeline module that generates Layer 1 (factual) and Layer 2 (AI narrative) bios.

**Files:**
- Create: `src/bio_generator.py`
- Test: `tests/test_bio_generator.py` (create)

**Step 1: Write the failing tests**

Create `tests/test_bio_generator.py`:

```python
"""Tests for bio generator pipeline module."""
import json
from unittest.mock import patch, MagicMock
from src.bio_generator import build_factual_profile, generate_bio_summary, BIO_CONSTRAINTS


def test_build_factual_profile_basic():
    """Factual profile should include all expected fields."""
    profile = build_factual_profile(
        official_name="Jane Doe",
        official_role="councilmember",
        official_seat="District 1",
        term_start="2023-01-10",
        term_end=None,
        vote_count=487,
        meetings_attended=22,
        meetings_total=24,
        top_categories=[
            {"category": "contracts", "count": 98},
            {"category": "governance", "count": 72},
        ],
        majority_alignment_rate=0.89,
        sole_dissent_count=12,
        sole_dissent_categories=[
            {"category": "budget", "count": 5},
            {"category": "infrastructure", "count": 4},
        ],
    )

    assert profile["name"] == "Jane Doe"
    assert profile["role"] == "councilmember"
    assert profile["seat"] == "District 1"
    assert profile["term_start"] == "2023-01-10"
    assert profile["vote_count"] == 487
    assert profile["attendance_rate"] == "92%"
    assert profile["attendance_fraction"] == "22 of 24"
    assert profile["majority_alignment_rate"] == "89%"
    assert len(profile["top_categories"]) == 2
    assert profile["sole_dissent_count"] == 12


def test_build_factual_profile_zero_meetings():
    """Handle zero meetings without division by zero."""
    profile = build_factual_profile(
        official_name="Test",
        official_role="councilmember",
        official_seat=None,
        term_start=None,
        term_end=None,
        vote_count=0,
        meetings_attended=0,
        meetings_total=0,
        top_categories=[],
        majority_alignment_rate=0.0,
        sole_dissent_count=0,
        sole_dissent_categories=[],
    )
    assert profile["attendance_rate"] == "0%"
    assert profile["attendance_fraction"] == "0 of 0"


def test_bio_constraints_exist():
    """Constraints string should include key guardrails."""
    assert "political orientation" in BIO_CONSTRAINTS.lower()
    assert "compare" in BIO_CONSTRAINTS.lower()
    assert "value-laden" in BIO_CONSTRAINTS.lower()


def test_generate_bio_summary_calls_api():
    """generate_bio_summary should call the Claude API with factual data."""
    mock_profile = {
        "name": "Jane Doe",
        "role": "councilmember",
        "vote_count": 100,
        "attendance_rate": "90%",
        "attendance_fraction": "18 of 20",
        "top_categories": [{"category": "budget", "count": 30}],
        "majority_alignment_rate": "85%",
        "sole_dissent_count": 5,
        "sole_dissent_categories": [{"category": "budget", "count": 3}],
    }

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Jane Doe has participated in 18 of 20 meetings.")]
    mock_response.model = "claude-sonnet-4-5-20250514"

    with patch("src.bio_generator.anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        result = generate_bio_summary(mock_profile)

        assert result["summary"] == "Jane Doe has participated in 18 of 20 meetings."
        assert result["model"] == "claude-sonnet-4-5-20250514"
        # Verify constraints were passed in the prompt
        call_args = mock_client.messages.create.call_args
        prompt_text = call_args.kwargs["messages"][0]["content"]
        assert "political orientation" in prompt_text.lower()
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_bio_generator.py -v`
Expected: FAIL (module not found)

**Step 3: Write the bio generator**

Create `src/bio_generator.py`:

```python
"""
Bio generator for council member profiles.

Two-layer structure:
- Layer 1 (Factual): Pure data aggregation from database queries. No AI inference.
- Layer 2 (Summary): AI-synthesized narrative with mandatory transparency disclosure.

Publication tiers:
- Layer 1: Public (factual, no judgment)
- Layer 2: Graduated (operator reviews before public exposure)
"""

from datetime import datetime, timezone
from typing import Any

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]


BIO_CONSTRAINTS = """Constraints on the summary:
- State what the data shows. Do not interpret why.
- Do not characterize political orientation or ideology.
- Do not compare members to each other.
- Do not use value-laden language (good/bad, strong/weak, effective/ineffective).
- Write in third person.
- Keep to 2-3 sentences maximum.
- Focus on participation patterns and voting record facts."""


def build_factual_profile(
    *,
    official_name: str,
    official_role: str,
    official_seat: str | None,
    term_start: str | None,
    term_end: str | None,
    vote_count: int,
    meetings_attended: int,
    meetings_total: int,
    top_categories: list[dict[str, Any]],
    majority_alignment_rate: float,
    sole_dissent_count: int,
    sole_dissent_categories: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build Layer 1 factual profile from database query results.

    No AI inference. No editorial judgment. Pure data aggregation.
    """
    attendance_rate = (
        round(meetings_attended / meetings_total * 100)
        if meetings_total > 0
        else 0
    )

    return {
        "name": official_name,
        "role": official_role,
        "seat": official_seat,
        "term_start": term_start,
        "term_end": term_end,
        "vote_count": vote_count,
        "attendance_rate": f"{attendance_rate}%",
        "attendance_fraction": f"{meetings_attended} of {meetings_total}",
        "top_categories": top_categories,
        "majority_alignment_rate": f"{round(majority_alignment_rate * 100)}%",
        "sole_dissent_count": sole_dissent_count,
        "sole_dissent_categories": sole_dissent_categories,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def generate_bio_summary(factual_profile: dict[str, Any]) -> dict[str, Any]:
    """Generate Layer 2 AI-synthesized narrative from factual data.

    Requires ANTHROPIC_API_KEY in environment.
    Returns dict with 'summary' and 'model' keys.
    """
    if anthropic is None:
        raise ImportError("anthropic package required for bio generation")

    client = anthropic.Anthropic()

    name = factual_profile["name"]
    prompt = f"""Based on the following factual voting record data, write a brief summary paragraph (2-3 sentences) about this council member's participation.

Factual data:
- Name: {name}
- Role: {factual_profile.get("role", "councilmember")}
- Votes cast: {factual_profile["vote_count"]}
- Attendance: {factual_profile["attendance_fraction"]} meetings ({factual_profile["attendance_rate"]})
- Top categories by vote count: {", ".join(f'{c["category"]} ({c["count"]})' for c in factual_profile.get("top_categories", []))}
- Voted with majority: {factual_profile["majority_alignment_rate"]}
- Sole dissenting vote: {factual_profile["sole_dissent_count"]} times
- Sole dissent topics: {", ".join(f'{c["category"]} ({c["count"]})' for c in factual_profile.get("sole_dissent_categories", []))}

{BIO_CONSTRAINTS}"""

    response = client.messages.create(
        model="claude-sonnet-4-5-20250514",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    return {
        "summary": response.content[0].text,
        "model": response.model,
    }
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_bio_generator.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add src/bio_generator.py tests/test_bio_generator.py
git commit -m "feat: add bio generator pipeline module with Layer 1/Layer 2 structure"
```

---

## Task 10: Render Layer 1 Factual Profile on Council Page

Display the factual profile data (from `bio_factual` JSONB column) on the council member page. This is Public tier, always visible.

**Files:**
- Create: `web/src/components/FactualProfile.tsx`
- Modify: `web/src/app/council/[slug]/page.tsx`

**Step 1: Create FactualProfile component**

Create `web/src/components/FactualProfile.tsx`:

```tsx
interface FactualProfileProps {
  bioFactual: Record<string, unknown> | null
}

export default function FactualProfile({ bioFactual }: FactualProfileProps) {
  if (!bioFactual) return null

  const fields = [
    { label: 'Term', value: bioFactual.term_start ? `Since ${String(bioFactual.term_start).slice(0, 4)}` : null },
    { label: 'Votes Cast', value: bioFactual.vote_count },
    { label: 'Attendance', value: `${bioFactual.attendance_fraction} meetings (${bioFactual.attendance_rate})` },
    { label: 'Majority Alignment', value: bioFactual.majority_alignment_rate },
    { label: 'Sole Dissents', value: bioFactual.sole_dissent_count },
  ].filter((f) => f.value != null && f.value !== 0)

  const topCategories = (bioFactual.top_categories as { category: string; count: number }[]) ?? []

  return (
    <section className="mb-8">
      <h2 className="text-xl font-semibold text-slate-800 mb-3">Profile Summary</h2>
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <dl className="grid grid-cols-2 sm:grid-cols-3 gap-4">
          {fields.map((f) => (
            <div key={f.label}>
              <dt className="text-xs text-slate-500">{f.label}</dt>
              <dd className="text-sm font-medium text-slate-800">{String(f.value)}</dd>
            </div>
          ))}
        </dl>
        {topCategories.length > 0 && (
          <div className="mt-3 pt-3 border-t border-slate-100">
            <p className="text-xs text-slate-500 mb-1">Most Active In</p>
            <p className="text-sm text-slate-800">
              {topCategories.slice(0, 5).map((c) =>
                `${c.category.replace(/_/g, ' ')} (${c.count})`
              ).join(', ')}
            </p>
          </div>
        )}
        {bioFactual.generated_at && (
          <p className="text-xs text-slate-400 mt-3">
            Data as of {new Date(String(bioFactual.generated_at)).toLocaleDateString()}
          </p>
        )}
      </div>
    </section>
  )
}
```

**Step 2: Wire into council profile page**

In `web/src/app/council/[slug]/page.tsx`, add import:

```typescript
import FactualProfile from '@/components/FactualProfile'
```

Add after the stats bar section (before or after the CategoryBreakdown):

```tsx
      {/* Factual Profile (Layer 1 - Public) */}
      <FactualProfile bioFactual={official.bio_factual ?? null} />
```

Note: `official` comes from `getOfficialWithStats()` which does `select('*')`, so `bio_factual` will be included after the migration runs.

**Step 3: Verify build**

Run: `cd web && npx next build`
Expected: Build succeeds

**Step 4: Commit**

```bash
git add web/src/components/FactualProfile.tsx "web/src/app/council/[slug]/page.tsx"
git commit -m "feat: render Layer 1 factual profile on council member pages"
```

---

## Task 11: Render Layer 2 AI Summary Behind Operator Gate

Display the AI-generated bio summary on the council page, gated behind OperatorGate (Graduated tier). Includes mandatory transparency disclosure.

**Files:**
- Create: `web/src/components/BioSummary.tsx`
- Modify: `web/src/app/council/[slug]/page.tsx`

**Step 1: Create BioSummary component**

Create `web/src/components/BioSummary.tsx`:

```tsx
import OperatorGate from './OperatorGate'

interface BioSummaryProps {
  bioSummary: string | null
  bioGeneratedAt: string | null
  bioModel: string | null
  officialName: string
  meetingCount: number
}

export default function BioSummary({
  bioSummary,
  bioGeneratedAt,
  bioModel,
  officialName,
  meetingCount,
}: BioSummaryProps) {
  if (!bioSummary) return null

  return (
    <OperatorGate>
      <section className="mb-8">
        <div className="flex items-center gap-2 mb-3">
          <h2 className="text-xl font-semibold text-slate-800">AI Summary</h2>
          <span className="text-xs bg-amber-100 text-amber-800 px-2 py-0.5 rounded font-medium">
            Operator Only
          </span>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <p className="text-sm text-slate-800 leading-relaxed">{bioSummary}</p>
          <hr className="my-3 border-slate-100" />
          <p className="text-xs text-slate-400 leading-relaxed">
            This summary was generated by AI based on {officialName}&apos;s voting record
            across {meetingCount} meetings. It reflects patterns in official vote data,
            not editorial judgment.
            <br />
            Data sources: City of Richmond certified meeting minutes
            {bioGeneratedAt && (
              <>
                <br />
                Last updated: {new Date(bioGeneratedAt).toLocaleDateString()}
              </>
            )}
            {bioModel && (
              <>
                <br />
                Model: {bioModel}
              </>
            )}
          </p>
        </div>
      </section>
    </OperatorGate>
  )
}
```

**Step 2: Wire into council profile page**

In `web/src/app/council/[slug]/page.tsx`, add import:

```typescript
import BioSummary from '@/components/BioSummary'
```

Add after the FactualProfile section:

```tsx
      {/* AI Bio Summary (Layer 2 - Graduated, Operator Only) */}
      <BioSummary
        bioSummary={official.bio_summary ?? null}
        bioGeneratedAt={official.bio_generated_at ?? null}
        bioModel={official.bio_model ?? null}
        officialName={official.name}
        meetingCount={stats?.meetings_total ?? 0}
      />
```

**Step 3: Verify build**

Run: `cd web && npx next build`
Expected: Build succeeds

**Step 4: Commit**

```bash
git add web/src/components/BioSummary.tsx "web/src/app/council/[slug]/page.tsx"
git commit -m "feat: render Layer 2 AI bio summary behind operator gate"
```

---

## Task 12: Run All Tests and Final Build

**Step 1: Run Python tests**

Run: `python3 -m pytest tests/ -q --tb=short`
Expected: All tests pass (existing + new)

**Step 2: Run frontend build**

Run: `cd web && npx next build`
Expected: Build succeeds with no errors

**Step 3: Final commit if any fixes were needed**

If any tests failed or build errors occurred, fix and commit:

```bash
git add -A
git commit -m "fix: resolve test/build issues from Sprint 2 implementation"
```

---

## Post-Implementation: Manual Steps

These require human action and are NOT part of the automated plan:

1. **Run migration 006** in Supabase SQL Editor
2. **Spot-check backfill:** Review the ~58 reclassified items to confirm they're genuinely appointment-related
3. **Run bio generator** against live data: `python3 -c "from src.bio_generator import ..."`  (requires ANTHROPIC_API_KEY)
4. **Review Layer 2 bios** in operator mode before graduating any to public

---

## Summary

| Task | What | Sprint Item |
|------|------|-------------|
| 1 | Add `APPOINTMENTS` to Python enum | S2.1 |
| 2 | Update extraction schema (both locations) | S2.1 |
| 3 | DB migration: backfill + bio columns | S2.1 + S2.3 |
| 4 | Align CategoryBadge frontend colors | S2.1 |
| 5 | Category badge on ConflictFlagCard | S2.2 |
| 6 | Category chips on meetings list | S2.2 |
| 7 | Category breakdown on council profile | S2.2 |
| 8 | Bio fields in TypeScript types | S2.3 |
| 9 | Bio generator pipeline module | S2.3 |
| 10 | Render Layer 1 factual profile | S2.3 |
| 11 | Render Layer 2 AI summary (operator gate) | S2.3 |
| 12 | Run all tests + final build | All |
