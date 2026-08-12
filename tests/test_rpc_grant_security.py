"""Safety contract for the forward RPC EXECUTE-grant allowlist."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "src" / "migrations" / "138_restrict_rpc_execute_grants.sql"
MIRROR = ROOT / "supabase" / "migrations" / "20260810013800_restrict_rpc_execute_grants.sql"
FORBIDDEN_134 = ROOT / "docs" / "plans" / "134_source_reconciliation_enforcement.sql"

PUBLIC_READ_RPCS = {
    "find_similar_items", "get_category_stats", "get_contested_votes",
    "get_controversial_items", "get_divergent_motions_detail",
    "get_meeting_counts", "get_meeting_flag_counts", "list_public_tables",
    "parse_vote_tally", "search_hybrid", "search_site",
}
INTERNAL_RPCS = {
    "check_and_increment_rate_limit", "cleanup_rate_limit_buckets",
    "merge_official_pair", "rls_auto_enable", "update_meeting_agenda_item_count",
}


def _sql_without_comments() -> str:
    return "\n".join(
        line for line in SOURCE.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    )


def test_rpc_grant_migration_is_mirrored_exactly():
    assert SOURCE.read_bytes() == MIRROR.read_bytes()


def test_migration_134_remains_byte_identical_to_forbidden_baseline():
    assert hashlib.sha256(FORBIDDEN_134.read_bytes()).hexdigest() == (
        "4fac27264b5b0fe63f03d92e52462db33590457c11de64e795f4daeb4072e7a6"
    )


def test_forward_migration_changes_privileges_only():
    sql = _sql_without_comments().upper()
    for forbidden in (
        "BEGIN;", "COMMIT;", "CREATE ", "ALTER ", "DROP ",
        "DELETE FROM", "TRUNCATE ", "UPDATE ", "INSERT INTO",
    ):
        assert forbidden not in sql


def test_public_rpcs_have_explicit_api_role_grants():
    sql = _sql_without_comments()
    for name in PUBLIC_READ_RPCS:
        assert re.search(
            rf"REVOKE ALL PRIVILEGES ON FUNCTION public\.{name}\b"
            rf"[\s\S]*?FROM PUBLIC, anon, authenticated;",
            sql,
        )
        assert re.search(
            rf"GRANT EXECUTE ON FUNCTION public\.{name}\b"
            rf"[\s\S]*?TO anon, authenticated, service_role;",
            sql,
        )


def test_internal_functions_are_not_granted_to_api_roles():
    sql = _sql_without_comments()
    for name in INTERNAL_RPCS:
        assert re.search(
            rf"REVOKE ALL PRIVILEGES ON FUNCTION public\.{name}\b"
            rf"[\s\S]*?FROM PUBLIC, anon, authenticated",
            sql,
        )
        grant = re.search(
            rf"GRANT EXECUTE ON FUNCTION public\.{name}\b"
            rf"[\s\S]*?TO ([^;]+);",
            sql,
        )
        if grant:
            roles = {role.strip() for role in grant.group(1).split(",")}
            assert "anon" not in roles
            assert "authenticated" not in roles
