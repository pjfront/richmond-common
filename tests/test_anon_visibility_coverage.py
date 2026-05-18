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

from test_anon_visibility import PUBLIC_TABLES

_ROOT = Path(__file__).parent.parent
_QUERIES_DIR = _ROOT / "web" / "src" / "lib" / "queries"

# ── Classification sets ──────────────────────────────────────────────
#
# Every table referenced from `web/src/lib/queries/*.ts` must appear in
# exactly one of three places:
#
#   1. PUBLIC_TABLES (in test_anon_visibility.py) — the default. Adding
#      X here also adds an HTTP test that asserts anon can SELECT X.
#   2. EXEMPT (below) — only when the queries.ts call is genuinely not
#      anon-facing (e.g., reached only by a server-side admin path).
#      Reason must be documented inline.
#   3. KNOWN_COVERAGE_GAPS (below) — transitional debt. Tables that
#      queries.ts already read at the time this test landed (2026-05-18)
#      but PUBLIC_TABLES didn't yet cover. Locked here so the gap can
#      shrink but cannot grow. New code must NOT use this path.

EXEMPT: dict[str, str] = {
    # No exemptions today. The default for any queries.ts table is to be
    # tested for anon visibility — queries.ts is the anon-facing data
    # layer by construction. An entry here means "this query path is
    # reached only by server-side code that uses the service-role
    # client" or similar; add the reason as the value.
}

# Backsliding-guarded debt. Each entry is a queries.ts `.from()` call
# that the existing `tests/test_anon_visibility.py::PUBLIC_TABLES` test
# does NOT yet assert anon can read. New code must NOT add to this set
# — extend PUBLIC_TABLES or EXEMPT instead.
#
# Initial population (2026-05-18) was 14 entries. The 11 mechanical
# wins (anon policy present + table populated) were moved to
# PUBLIC_TABLES the same day after a direct probe via
# `SET LOCAL ROLE anon` confirmed each returns rows. The 3 remaining
# entries each need different work — they are NOT just "add to
# PUBLIC_TABLES" cases:
#
#   community_comments
#     The queries/comments.ts, components/CommunityCommentSection.tsx,
#     and api/community-comments/route.ts all reference this table.
#     Migration 108_community_comments.sql is in src/migrations/. BUT
#     the table DOES NOT EXIST in production — supabase_migrations
#     shows `community_voice` (the pre-rename name?) was applied, not
#     `community_comments`. The community-voice feature is half-shipped:
#     frontend code exists, schema does not. Adding to PUBLIC_TABLES
#     would fail with "relation does not exist." Resolving needs an
#     operator decision: (a) ship migration 108 to production, or
#     (b) gate/remove the frontend code paths. Tracked in
#     docs/AI-PARKING-LOT.md.
#
#   filing_period_briefings
#     Anon CAN SELECT (policy exists, named "Public read public-tier
#     briefings") but the policy filters to
#     `publication_tier = 'public' AND is_current`. As of 2026-05-18
#     the table has 92 rows total, all at `graduated` tier, so anon
#     sees 0 rows. Adding to PUBLIC_TABLES would fail the strict
#     `>=1 row` assertion by design — the operator hasn't promoted any
#     briefings to public tier yet. The test's "1+ row" check is the
#     wrong shape for tables with conditional-publication RLS; needs a
#     soft variant ("HTTP 200, row count not asserted") or a real
#     public-tier briefing to exist first.
#
#   v_commission_staleness
#     Postgres view (not a table). RLS on views inherits from the
#     underlying tables (commissions, commission_members — both
#     anon-readable). View definition is filtered by
#     `HAVING count(... WHERE website_stale_since IS NOT NULL) > 0`,
#     so only commissions with stale members appear. As of 2026-05-18
#     no commission has stale members, so anon sees 0 rows. Same shape
#     as filing_period_briefings: anon CAN read, but row count depends
#     on real-world state.
KNOWN_COVERAGE_GAPS: frozenset[str] = frozenset({
    "community_comments",
    "filing_period_briefings",
    "v_commission_staleness",
})

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
      1. Default: add X to PUBLIC_TABLES in tests/test_anon_visibility.py.
         The HTTP test then asserts anon can SELECT X against live
         Supabase, surfacing any missing RLS policy.
      2. If X is genuinely server-side: add to EXEMPT with a reason.
      3. Transitional only (new code MUST NOT take this path): add to
         KNOWN_COVERAGE_GAPS with a TODO to shrink the set.
    """
    queried = _tables_referenced_in_queries()
    covered = set(PUBLIC_TABLES) | set(EXEMPT) | KNOWN_COVERAGE_GAPS
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
        f"-k {sorted(missing)[0]}` against live Supabase to verify the "
        f"anon role can actually read the table.\n"
        f"  - If the call is genuinely server-side / admin-only: add to "
        f"EXEMPT in tests/test_anon_visibility_coverage.py with a one-line "
        f"reason.\n"
        f"  - Transitional only: add to KNOWN_COVERAGE_GAPS with a TODO "
        f"to backfill PUBLIC_TABLES later. New code must NOT take this "
        f"path."
    )


def test_known_coverage_gaps_only_shrinks():
    """A table classified in both KNOWN_COVERAGE_GAPS and PUBLIC_TABLES/
    EXEMPT is leftover debt — the gap entry should have been removed
    when the table was properly classified.
    """
    classified_elsewhere = (set(PUBLIC_TABLES) | set(EXEMPT)) & KNOWN_COVERAGE_GAPS
    assert not classified_elsewhere, (
        f"Tables present in both PUBLIC_TABLES/EXEMPT AND "
        f"KNOWN_COVERAGE_GAPS: {sorted(classified_elsewhere)}.\n\n"
        f"The gap allowlist is for tables NOT yet properly classified. "
        f"Once a table is in PUBLIC_TABLES or EXEMPT, remove it from "
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
