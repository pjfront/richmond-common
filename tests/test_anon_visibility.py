"""Layer 3 of the lineage system: anon-role visibility checks.

Static lineage (manifest) and liveness expectations (SQL checks) both run
as the service role — they bypass Row Level Security. This test harness
asks the question those layers can't: when a citizen visits the site, can
the anon Supabase client actually SEE the data?

This catches the RLS-policy-gap pattern from 2026-03-17, where 18 tables
had RLS enabled with zero policies. The pipeline wrote rows successfully
(via DATABASE_URL, direct Postgres). The anon client got `[]` empty arrays
back from PostgREST. No error. Just data, presented as absence.

Skip behavior: tests skip cleanly if SUPABASE_URL or SUPABASE_ANON_KEY are
not set, so CI runs without secrets don't fail noisily.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env", override=True)
# Frontend keeps the anon key under NEXT_PUBLIC_ prefix in web/.env.local
load_dotenv(_ROOT / "web" / ".env.local", override=False)

SUPABASE_URL = (
    os.getenv("SUPABASE_URL")
    or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
)
SUPABASE_ANON_KEY = (
    os.getenv("SUPABASE_ANON_KEY")
    or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
)


def _is_placeholder(url: str | None, key: str | None) -> bool:
    """CI sets these to literal 'test...' values when no real Supabase is wired."""
    if not (url and key):
        return True
    if "test.supabase.co" in url:
        return True
    if key in {"test-anon-key", "test"}:
        return True
    return False


pytestmark = pytest.mark.skipif(
    _is_placeholder(SUPABASE_URL, SUPABASE_ANON_KEY),
    reason="SUPABASE_URL or SUPABASE_ANON_KEY missing or placeholder (CI without secrets)",
)


# Most public tables have a UUID `id` PK. Tables that use a different
# column name as PK (or views without an id projection) need an explicit
# override — without it, PostgREST returns HTTP 400 on `?select=id` and
# the test reads it as an RLS regression rather than the column-name
# mismatch it actually is.
# Added 2026-05-22: form_summary_cache uses filing_id (its natural key
# from NetFile); v_commission_staleness is a view that aggregates from
# commissions and projects commission_id instead of id. Both previously
# gave false negatives reading column-name 400s as RLS regressions.
_ANON_SELECT_COLUMN: dict[str, str] = {
    "finance_public_events": "event_key",
    "finance_public_coverage": "scope_key",
    "form_summary_cache": "filing_id",
    "v_commission_staleness": "commission_id",
}


def _anon_select(table: str, query: str | None = None) -> tuple[int, list]:
    """Query a table as the anon role, return (status_code, rows)."""
    if query is None:
        column = _ANON_SELECT_COLUMN.get(table, "id")
        query = f"select={column}&limit=1"
    url = f"{SUPABASE_URL}/rest/v1/{table}?{query}"
    resp = requests.get(
        url,
        headers={
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        },
        timeout=10,
    )
    if resp.status_code >= 400:
        return resp.status_code, []
    return resp.status_code, resp.json()


# ── Public-facing tables that MUST be readable by anon role ──
#
# When a citizen loads the site, queries.ts hits PostgREST with the anon
# key. If RLS blocks any of these tables, that page renders empty without
# any error — the silent failure pattern we want to prevent.

PUBLIC_TABLES = [
    "meetings",
    "agenda_items",
    "motions",
    "votes",
    "public_comments",
    "contributions",
    "donors",
    "committees",
    "conflict_flags",
    "nextrequest_requests",
    "officials",
    "elections",
    "election_candidates",
    "data_sync_log",
    "scan_runs",
    "documents",
    # form_summary_cache: added 2026-05-18 (migration 116) after the
    # D56b Option 1 anon-visibility bug. The candidate-profile page reads
    # this table via anon to display each candidate's Form 460 cycle-to-
    # date as their headline total. Without anon SELECT, the Option 1
    # helper falls back to summing DB rows and the page shows the wrong
    # number silently — exactly the failure mode this test exists to
    # catch.
    "form_summary_cache",
    # ── Batch added 2026-05-18: backfilled from KNOWN_COVERAGE_GAPS in
    # tests/test_anon_visibility_coverage.py. Each was already queried
    # from web/src/lib/queries/*.ts and has anon-readable RLS policies
    # confirmed via SET LOCAL ROLE anon + count probe. Adding here moves
    # them from "static-analysis-acknowledged debt" to "HTTP-asserted
    # working." The static-analysis test's KNOWN_COVERAGE_GAPS allowlist
    # was correspondingly shrunk in the same commit.
    "behested_payments",
    "bodies",
    "closed_session_items",
    "comment_theme_assignments",
    "commission_members",
    "commissions",
    "economic_interests",
    "form700_filings",
    "independent_expenditures",
    "item_theme_narratives",
    "meeting_attendance",
    "neighborhood_councils",
    "city_contracts",
    "business_entities",
    "entity_name_matches",
]


# ── Tables with conditional-data RLS (anon can reach, rows may be empty) ──
#
# Some tables have RLS policies that filter rows by publication state or
# real-world conditions, not by role. Anon CAN reach the table (no
# 401/403/4xx), but a legitimate empty result is possible depending on
# what data has been promoted/exists right now. For these, the strict
# `>=1 row` assertion in test_anon_can_read_table is the wrong shape — a
# graduated-but-not-yet-public briefing or a no-stale-members snapshot
# would flag as a bug when neither is. The softer check below asserts
# anon access reaches the table at all (HTTP 200), which is what catches
# the D56b shape (RLS blocks anon entirely → 4xx or empty PostgREST
# response on a populated table).
#
# Promotion path: when a table here gets a row that anon should always
# see (e.g., once a filing_period_briefing is promoted to public tier),
# move it to PUBLIC_TABLES so the stricter check applies.
PUBLIC_TABLES_CONDITIONAL = [
    "civic_brief_candidates",  # Only reviewed, published versions are visible.
    "finance_public_events",  # Published only after source assertions reconcile.
    "finance_public_coverage",  # Empty until the first bounded snapshot succeeds.
    # filing_period_briefings: policy is
    #   USING (publication_tier = 'public' AND is_current)
    # As of 2026-05-18, all 92 rows are at `graduated` tier; anon sees 0.
    # The page still calls .from('filing_period_briefings') — RLS access
    # is the gate we test here; row count depends on operator promotion.
    "filing_period_briefings",
    # v_commission_staleness: view aggregating commissions +
    # commission_members with `HAVING count(... stale) > 0`. Currently no
    # commission has stale members → 0 rows even with full anon access.
    # When a commission roster goes stale, the view auto-populates.
    "v_commission_staleness",
]


@pytest.mark.parametrize("table", PUBLIC_TABLES_CONDITIONAL)
def test_anon_can_query_conditional_table(table: str):
    """Anon role must reach the table (HTTP 200); rows may be empty.

    For tables whose anon-visible rows depend on real-world publication
    state (publication_tier filter, view HAVING clause, etc.). RLS still
    gates *access*; data state gates row count. A 4xx response or a
    PostgREST-level error here is the regression we catch — that's the
    D56b shape where the anon role can't reach the table at all.

    A 200-with-[] is acceptable here. If a row should always be visible,
    promote the entry to PUBLIC_TABLES so the strict check applies.
    """
    status, _ = _anon_select(table)
    assert status == 200, (
        f"Anon SELECT on {table} returned HTTP {status}. RLS or policy "
        f"regression — anon role can no longer reach the table at all."
    )


@pytest.mark.parametrize("table", PUBLIC_TABLES)
def test_anon_can_read_table(table: str):
    """Anon role must get at least one row from each public table.

    A 200 with `[]` is the silent-failure mode — there ARE rows in the
    DB but RLS is blocking them. This test fails loud in that case.
    """
    status, rows = _anon_select(table)
    assert status == 200, (
        f"Anon SELECT on {table} returned HTTP {status}. "
        f"Check RLS policies and migration coverage."
    )
    assert len(rows) >= 1, (
        f"Anon SELECT on {table} returned 0 rows. Either the table is "
        f"empty (unlikely for these public tables) or RLS is blocking "
        f"the anon role. Add a 'Public read' policy in a new migration."
    )


def test_anon_can_read_recent_meeting():
    """Most recent regular council meeting must be visible to anon role.

    More specific than the general 'meetings' check — verifies the latest
    record (the one users will look at first) is reachable.
    """
    query = (
        "select=id,meeting_date"
        "&meeting_type=eq.regular"
        "&city_fips=eq.0660620"
        "&order=meeting_date.desc"
        "&limit=1"
    )
    status, rows = _anon_select("meetings", query)
    assert status == 200
    assert len(rows) == 1, (
        "Most recent regular council meeting not visible to anon role. "
        "Either no meetings exist (broken pipeline) or RLS is blocking."
    )


def test_anon_can_read_current_council():
    """Current council members must be listable by anon role."""
    query = (
        "select=id,name,role"
        "&is_current=eq.true"
        "&city_fips=eq.0660620"
    )
    status, rows = _anon_select("officials", query)
    assert status == 200
    # Richmond has 7 council seats + mayor
    assert len(rows) >= 5, (
        f"Only {len(rows)} current council members visible to anon role "
        f"(expected >= 5). Check officials seeding and RLS."
    )


def test_anon_can_read_current_conflict_flags():
    """Public conflict flags (is_current=TRUE) must be visible.

    Catches the RLS bug shape: data exists, but anon role sees [].
    """
    query = "select=id&is_current=eq.true&city_fips=eq.0660620&limit=1"
    status, rows = _anon_select("conflict_flags", query)
    assert status == 200
    assert len(rows) >= 1, (
        "No current conflict_flags visible to anon role. Either scanner "
        "has not run successfully or RLS is blocking the anon view."
    )
