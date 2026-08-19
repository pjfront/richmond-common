"""Safety contracts for the bounded November public read-path work."""

from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).parents[1]
SEARCH_SOURCE = ROOT / "src" / "migrations" / "143_harden_search_read_paths.sql"
SEARCH_MIRROR = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260818014300_harden_search_read_paths.sql"
)
VOTES_SOURCE = ROOT / "src" / "migrations" / "144_official_voting_record_rpc.sql"
VOTES_MIRROR = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260818014400_official_voting_record_rpc.sql"
)
FORBIDDEN_134 = ROOT / "docs" / "plans" / "134_source_reconciliation_enforcement.sql"


def _without_line_comments(path: Path) -> str:
    return "\n".join(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    )


def test_new_read_path_migrations_are_mirrored_byte_identically():
    assert SEARCH_SOURCE.read_bytes() == SEARCH_MIRROR.read_bytes()
    assert VOTES_SOURCE.read_bytes() == VOTES_MIRROR.read_bytes()


def test_migration_134_remains_the_forbidden_byte_identical_artifact():
    # Git checks the artifact in with LF. Windows autocrlf changes only the
    # worktree representation, so normalize that checkout-only difference.
    canonical_bytes = FORBIDDEN_134.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(canonical_bytes).hexdigest() == (
        "4fac27264b5b0fe63f03d92e52462db33590457c11de64e795f4daeb4072e7a6"
    )


def test_search_rewrite_is_bounded_read_only_and_hardened():
    sql = SEARCH_SOURCE.read_text(encoding="utf-8")
    executable = _without_line_comments(SEARCH_SOURCE).upper()

    assert sql.count("\nSECURITY DEFINER\n") == 4
    assert sql.count("SET search_path = pg_catalog, pg_temp") == 4
    assert "v_query := left(trim(coalesce(p_query, '')), 200);" in sql
    assert "v_limit := least(greatest(coalesce(p_limit, 20), 1), 250);" in sql
    assert "least(greatest(coalesce(p_limit, 20), 1), 50)" in sql
    assert "v_offset := least(greatest(coalesce(p_offset, 0), 0), 200);" in sql
    assert "v_limit := least(greatest(coalesce(p_limit, 5), 1), 10);" in sql
    assert sql.count("AS MATERIALIZED") >= 7
    assert sql.count("LIMIT v_candidate_limit") >= 9
    assert sql.count("regexp_replace(lower(ofc.name), '\\s+', '-', 'g')") == 2
    assert "FROM public._search_site_candidates(" in sql
    assert (
        "ORDER BY candidates.relevance_score DESC, candidates.result_type, "
        "candidates.id;"
    ) in sql
    assert (
        "REVOKE ALL PRIVILEGES ON FUNCTION public._search_site_candidates("
        in sql
    )
    assert "GRANT EXECUTE ON FUNCTION public._search_site_candidates" not in sql
    assert ") FROM PUBLIC, anon, authenticated, service_role;" in sql
    assert "OPERATOR(extensions.<=>)" in sql

    # SECURITY DEFINER must duplicate the current-source visibility boundary.
    assert sql.count("source_cancelled_at IS NULL") >= 8
    assert sql.count("agenda_source_retired_at IS NULL") >= 6
    for table in (
        "public.agenda_items",
        "public.meetings",
        "public.motions",
        "public.officials",
        "public.agenda_items_embeddings",
        "public.motions_embeddings",
        "public.officials_embeddings",
        "public.meetings_embeddings",
    ):
        assert table in sql

    for function in ("search_site", "search_hybrid", "find_similar_items"):
        assert f"CREATE OR REPLACE FUNCTION public.{function}" in sql
        assert f"REVOKE ALL PRIVILEGES ON FUNCTION public.{function}" in sql
        assert f"GRANT EXECUTE ON FUNCTION public.{function}" in sql

    for forbidden in (
        "INSERT INTO",
        "UPDATE PUBLIC.",
        "DELETE FROM",
        "TRUNCATE ",
        "ALTER TABLE",
    ):
        assert forbidden not in executable

    # This reliability migration cannot make editorial/model-policy decisions.
    assert "CONFLICT_FLAGS" not in executable
    assert "DEEPSEEK" not in executable
    assert "LUNA" not in executable


def test_flat_voting_rpc_preserves_visibility_and_split_vote_semantics():
    sql = VOTES_SOURCE.read_text(encoding="utf-8")
    executable = _without_line_comments(VOTES_SOURCE).upper()

    assert sql.count("\nSECURITY DEFINER\n") == 1
    assert sql.count("SET search_path = pg_catalog, pg_temp") == 1
    assert "member_vote.official_id = p_official_id" in sql
    assert "mt.city_fips = '0660620'" in sql
    assert "mt.source_cancelled_at IS NULL" in sql
    assert "ai.agenda_source_retired_at IS NULL" in sql
    assert "EXISTS (" in sql
    assert "motion_vote.motion_id = mo.id" in sql
    assert "lower(motion_vote.vote_choice) = 'nay'" in sql
    assert "REVOKE ALL PRIVILEGES ON FUNCTION public.get_official_voting_record" in sql
    assert "TO anon, authenticated, service_role;" in sql

    for forbidden in ("INSERT INTO", "UPDATE PUBLIC.", "DELETE FROM", "TRUNCATE "):
        assert forbidden not in executable


def test_persistent_cache_ttls_are_named_and_wired_to_the_reads():
    policy = (ROOT / "web" / "src" / "lib" / "read-path-cache.ts").read_text(
        encoding="utf-8"
    )
    council = (ROOT / "web" / "src" / "lib" / "queries" / "council.ts").read_text(
        encoding="utf-8"
    )
    search = (ROOT / "web" / "src" / "lib" / "queries" / "search.ts").read_text(
        encoding="utf-8"
    )

    assert "OFFICIALS_CACHE_SECONDS = 24 * 60 * 60" in policy
    assert "SIMILAR_ITEMS_CACHE_SECONDS = 7 * 24 * 60 * 60" in policy
    assert "['full-officials-read-v1']" in council
    assert "{ revalidate: OFFICIALS_CACHE_SECONDS }" in council
    assert "['similar-items-read-v1']" in search
    assert "{ revalidate: SIMILAR_ITEMS_CACHE_SECONDS }" in search


def test_unavailable_reads_are_not_silently_rewritten_as_empty_results():
    council = (ROOT / "web" / "src" / "lib" / "queries" / "council.ts").read_text(
        encoding="utf-8"
    )
    search = (ROOT / "web" / "src" / "lib" / "queries" / "search.ts").read_text(
        encoding="utf-8"
    )
    route = (
        ROOT / "web" / "src" / "app" / "api" / "search" / "route.ts"
    ).read_text(encoding="utf-8")

    assert "failReadPath('Officials', error)" in council
    assert "failReadPath('Official voting record', error)" in council
    assert "failReadPath('Site search', error)" in search
    assert "failReadPath('Similar discussions', error)" in search
    assert "status: 503" in route
    assert "Search is temporarily unavailable." in route


def test_force_static_parents_do_not_cache_transient_read_fallbacks():
    council_page = (
        ROOT / "web" / "src" / "app" / "council" / "[slug]" / "page.tsx"
    ).read_text(encoding="utf-8")
    item_page = (
        ROOT
        / "web"
        / "src"
        / "app"
        / "meetings"
        / "[id]"
        / "items"
        / "[itemNumber]"
        / "page.tsx"
    ).read_text(encoding="utf-8")
    similar = (
        ROOT / "web" / "src" / "components" / "SimilarDiscussions.tsx"
    ).read_text(encoding="utf-8")

    # Uncaught render errors are the documented ISR signal: revalidation keeps
    # the last successful page, while an uncached first render fails honestly.
    for parent in (council_page, item_page):
        assert "export const dynamic = 'force-static'" in parent
        assert "export const revalidate = 86400" in parent

    assert (
        "const votingRecordPromise = getOfficialVotingRecord(official.id)"
        in council_page
    )
    assert ".catch(" not in council_page
    assert "await findSimilarItems(itemId, { limit })" in similar
    assert "catch (" not in similar
