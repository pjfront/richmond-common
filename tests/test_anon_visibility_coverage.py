"""Static-analysis layer for the anon-visibility test suite.

The lineage system has three runtime layers (manifest, SQL liveness,
HTTP anon-visibility); this is the fourth, pure-static layer. It
answers the question those three can't: "did we remember to register
the new query path for anon-visibility testing?"

Bug shape this catches (D56b follow-up, 2026-05-18):
  - Migration 114 created `form_summary_cache` with RLS enabled and only
    a service_role policy.
  - A new query `getLatestForm460Total` in `web/src/lib/queries/elections.ts`
    hit `form_summary_cache` via the anon Supabase client.
  - The table was NOT in `tests/test_anon_visibility.py::PUBLIC_TABLES`,
    so the HTTP-layer test never asserted anon could SELECT it.
  - Anon got `[]` back (no error — RLS returns empty for blocked rows),
    the candidate-profile fallback path took over, and the live site
    silently showed Anderson at $47,602 instead of $40,602 for ~24 hours
    until the operator spot-checked richmondcommons.org.

The fix (migration 116 + PUBLIC_TABLES update) was small. The lesson
was bigger: every new `.from('X')` in queries/*.ts must classify X for
anon visibility, and "remember to update PUBLIC_TABLES" is exactly the
discipline-based rule CLAUDE.md L34 warns about — it decays silently
because nothing checks it. This test is the mechanical enforcement.

This file does NOT make HTTP calls. It only reads TypeScript source.
It runs in every CI environment regardless of whether SUPABASE_URL is
configured. The complementary HTTP test (`test_anon_visibility.py`)
proves anon can actually read the registered tables; this test proves
the registration set is complete.
"""
from __future__ import annotations

import re
from pathlib import Path

from test_anon_visibility import PUBLIC_TABLES, PUBLIC_TABLES_CONDITIONAL

_ROOT = Path(__file__).parent.parent
_QUERIES_DIR = _ROOT / "web" / "src" / "lib" / "queries"

# ── Classification sets ──────────────────────────────────────────────
#
# Every table referenced from `web/src/lib/queries/*.ts` must appear in
# exactly one of four places:
#
#   1. PUBLIC_TABLES (in test_anon_visibility.py) — the default. Adding
#      X here also adds the strict HTTP test (anon SELECT must return
#      ≥1 row). Right for tables whose rows are always publication-ready.
#   2. PUBLIC_TABLES_CONDITIONAL (in test_anon_visibility.py) — for
#      tables where anon CAN reach the table but rows are conditional
#      on real-world state (publication_tier filter, view HAVING clause,
#      etc.). The soft test (HTTP 200, row count not asserted) still
#      catches the D56b shape of "RLS blocks anon entirely."
#   3. EXEMPT (below) — only when the queries.ts call is genuinely not
#      anon-facing (e.g., reached only by a server-side admin path).
#      Reason must be documented inline.
#   4. KNOWN_COVERAGE_GAPS (below) — transitional debt. Tables that
#      queries.ts already read at the time this test landed (2026-05-18)
#      but no anon-visibility test yet covers. Locked here so the gap
#      can shrink but cannot grow. New code must NOT use this path.

EXEMPT: dict[str, str] = {
    "community_comments": (
        "queries/comments.ts::getCommunityComments is defined but no "
        "longer called from any anon-reachable page as of 2026-05-18. "
        "The CommunityCommentSection in "
        "web/src/app/meetings/[id]/items/[itemNumber]/page.tsx is "
        "wrapped in OperatorGate and the server-side getCommunityComments "
        "call was removed. The API route /api/community-comments POST is "
        "wrapped in withOperatorAuth. The query function stays in "
        "queries.ts for future un-gating after migration 108 ships and "
        "S21 graduation review completes. See D60 in "
        "docs/AI-PARKING-LOT.md for the full history (Mar 28 2026 "
        "frontend wired without supabase/migrations/ mirror; "
        "community_comments table does not exist in production)."
    ),
}

# Backsliding-guarded debt. Each entry is a queries.ts `.from()` call
# that NO anon-visibility test yet covers. New code must NOT add to this
# set — extend PUBLIC_TABLES (strict), PUBLIC_TABLES_CONDITIONAL (soft),
# or EXEMPT instead.
#
# History:
#   - 2026-05-18 (initial): 14 entries.
#   - 2026-05-18 (same day): 11 backfilled to PUBLIC_TABLES after a
#     direct probe via `SET LOCAL ROLE anon` confirmed each returns rows.
#   - 2026-05-18 (later same day): 2 promoted to PUBLIC_TABLES_CONDITIONAL
#     after adding the soft-variant test for conditional-data tables.
#   - 2026-05-18 (D60 gate): community_comments moved to EXEMPT after
#     gating the frontend code path to operator mode. The static-
#     analysis pass is now clean (KNOWN_COVERAGE_GAPS = ∅).
KNOWN_COVERAGE_GAPS: frozenset[str] = frozenset()

# Same regex used by tests/test_d1_provenance.py. Kept duplicated rather
# than imported because the two tests audit different concerns and the
# couplings would obscure the dependency for future readers.
_FROM_PATTERN = re.compile(r"\.from\(['\"]([a-z_][a-z0-9_]*)['\"]")


def _tables_referenced_in_queries() -> set[str]:
    """Return the set of public tables referenced from queries/*.ts."""
    tables: set[str] = set()
    for path in _QUERIES_DIR.glob("*.ts"):
        tables.update(_FROM_PATTERN.findall(path.read_text(encoding="utf-8")))
    return tables


def test_every_queries_table_is_anon_visibility_covered():
    """Every `.from('X')` in queries/*.ts must classify X.

    A new query path that hits the anon client without anon-visibility
    coverage is the D56b silent-failure shape. This test makes that
    omission loud at PR review time instead of at production-spot-check
    time.

    Resolution paths (in order of preference):
      1. Default (strict): add X to PUBLIC_TABLES in
         tests/test_anon_visibility.py. The HTTP test asserts anon can
         SELECT X and gets >=1 row against live Supabase.
      2. Conditional-data: add to PUBLIC_TABLES_CONDITIONAL when anon
         CAN reach the table but rows are conditional on real-world
         state (publication-tier filter, view HAVING clause). Asserts
         HTTP 200 only.
      3. If X is genuinely server-side: add to EXEMPT with a reason.
      4. Transitional only (new code MUST NOT take this path): add to
         KNOWN_COVERAGE_GAPS with a TODO to shrink the set.
    """
    queried = _tables_referenced_in_queries()
    covered = (
        set(PUBLIC_TABLES)
        | set(PUBLIC_TABLES_CONDITIONAL)
        | set(EXEMPT)
        | KNOWN_COVERAGE_GAPS
    )
    missing = queried - covered

    assert not missing, (
        f"New table(s) referenced from web/src/lib/queries/*.ts but not "
        f"classified for anon-visibility testing: {sorted(missing)}.\n\n"
        f"This is the D56b silent-failure shape — a new query path hits "
        f"the anon Supabase client but anon-role RLS coverage was never "
        f"asserted, so a missing or wrong policy silently returns [] and "
        f"the page renders empty or wrong without any error.\n\n"
        f"Resolution:\n"
        f"  - Default: add to PUBLIC_TABLES in "
        f"tests/test_anon_visibility.py. Then run "
        f"`RICHMOND_RUN_DB_TESTS=1 pytest tests/test_anon_visibility.py "
        f"-k {sorted(missing)[0]}` against live Supabase to verify anon "
        f"can read >=1 row.\n"
        f"  - Conditional data (publication_tier filter, view HAVING, "
        f"etc.): add to PUBLIC_TABLES_CONDITIONAL — the soft test "
        f"asserts HTTP 200 but allows empty results.\n"
        f"  - Server-side / admin-only: add to EXEMPT in "
        f"tests/test_anon_visibility_coverage.py with a one-line reason.\n"
        f"  - Transitional only: add to KNOWN_COVERAGE_GAPS with a TODO "
        f"to backfill later. New code must NOT take this path."
    )


def test_known_coverage_gaps_only_shrinks():
    """A table classified in both KNOWN_COVERAGE_GAPS and one of the
    proper buckets (PUBLIC_TABLES, PUBLIC_TABLES_CONDITIONAL, EXEMPT)
    is leftover debt — the gap entry should have been removed when the
    table was properly classified.
    """
    properly_classified = (
        set(PUBLIC_TABLES) | set(PUBLIC_TABLES_CONDITIONAL) | set(EXEMPT)
    )
    classified_elsewhere = properly_classified & KNOWN_COVERAGE_GAPS
    assert not classified_elsewhere, (
        f"Tables present in both a proper bucket "
        f"(PUBLIC_TABLES/PUBLIC_TABLES_CONDITIONAL/EXEMPT) AND "
        f"KNOWN_COVERAGE_GAPS: {sorted(classified_elsewhere)}.\n\n"
        f"The gap allowlist is for tables NOT yet properly classified. "
        f"Once a table is in a proper bucket, remove it from "
        f"KNOWN_COVERAGE_GAPS in tests/test_anon_visibility_coverage.py "
        f"to lock in the win."
    )


def test_no_stale_exempt_or_gap_entries():
    """Entries in EXEMPT or KNOWN_COVERAGE_GAPS that no longer match a
    queries.ts reference are stale.

    If a query was removed from queries/*.ts, the corresponding
    classification entry serves no purpose — drop it.
    """
    queried = _tables_referenced_in_queries()
    stale_exempt = set(EXEMPT) - queried
    stale_gaps = KNOWN_COVERAGE_GAPS - queried
    stale = stale_exempt | stale_gaps
    assert not stale, (
        f"Entries in EXEMPT or KNOWN_COVERAGE_GAPS that no longer "
        f"appear in web/src/lib/queries/*.ts: {sorted(stale)}.\n\n"
        f"The query path was removed; the classification entry is now "
        f"dead. Drop the entry from "
        f"tests/test_anon_visibility_coverage.py."
    )
