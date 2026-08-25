"""Safety contract for the bounded public-view Security Advisor fix."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
SOURCE = (
    ROOT / "src" / "migrations" / "146_security_invoker_public_views.sql"
)
MIRROR = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260824014600_security_invoker_public_views.sql"
)
EXPECTED_VIEWS = (
    "v_permit_activity",
    "v_license_summary",
    "v_code_enforcement_summary",
    "v_behested_by_official",
    "v_lobbyist_clients",
    "v_body_meeting_counts",
    "v_body_roster",
    "v_entity_connections",
    "v_topic_stats",
)


def _executable_statements() -> list[str]:
    sql = "\n".join(
        line
        for line in SOURCE.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    )
    return [
        " ".join(statement.split())
        for statement in sql.split(";")
        if statement.strip()
    ]


def test_security_invoker_migration_is_mirrored_exactly():
    assert SOURCE.read_bytes() == MIRROR.read_bytes()


def test_only_the_nine_advisor_views_change_to_security_invoker():
    assert _executable_statements() == [
        f"ALTER VIEW public.{view} SET (security_invoker = true)"
        for view in EXPECTED_VIEWS
    ]


def test_migration_changes_reloptions_without_redefining_data_or_access():
    executable = "\n".join(_executable_statements()).upper()

    assert len(re.findall(r"\bALTER VIEW\b", executable)) == 9
    for forbidden in (
        "CREATE ",
        "DROP ",
        "GRANT ",
        "REVOKE ",
        "POLICY",
        "FUNCTION",
        "INSERT ",
        "UPDATE ",
        "DELETE ",
        "TRUNCATE ",
    ):
        assert forbidden not in executable


def test_rollback_is_explicit_and_restores_default_view_semantics():
    sql = SOURCE.read_text(encoding="utf-8")
    assert "ALTER VIEW public.<view_name> RESET (security_invoker);" in sql
