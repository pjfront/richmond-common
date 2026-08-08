"""Safety contract for the public whole-corpus statistics RPCs."""

import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "src" / "migrations" / "135_optimize_public_stats_rpcs.sql"
MIRROR = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260807013500_optimize_public_stats_rpcs.sql"
)


def test_public_stats_rpc_migration_is_mirrored_exactly():
    assert SOURCE.read_bytes() == MIRROR.read_bytes()


def test_security_definer_rpcs_keep_the_source_reconciliation_boundary():
    sql = SOURCE.read_text(encoding="utf-8")

    assert sql.count("\nSECURITY DEFINER\n") == 2
    assert sql.count("SET search_path = pg_catalog, pg_temp") == 2
    assert "mt.source_cancelled_at IS NULL" in sql
    assert "ai.agenda_source_retired_at IS NULL" in sql
    assert "cf.meeting_id IS NULL OR flag_meeting.id IS NOT NULL" in sql
    assert "cf.agenda_item_id IS NULL OR flag_item.id IS NOT NULL" in sql

    # A definer function must not remain executable by every database role.
    assert sql.count("REVOKE ALL ON FUNCTION") == 2
    assert sql.count("FROM PUBLIC;") == 2
    assert sql.count("TO anon, authenticated, service_role;") == 2


def test_definer_function_bodies_only_reference_schema_qualified_tables():
    sql = SOURCE.read_text(encoding="utf-8")

    for table_name in (
        "meetings",
        "agenda_items",
        "conflict_flags",
        "motions",
        "votes",
    ):
        assert f"public.{table_name}" in sql


def test_flag_rpc_preserves_threshold_and_zero_flag_meeting_behavior():
    """Performance work must not silently make a publication decision."""

    sql = SOURCE.read_text(encoding="utf-8")
    flag_body = sql.split(
        "CREATE OR REPLACE FUNCTION public.get_meeting_flag_counts", 1
    )[1].split("$function$;", 1)[0]

    # D2's 0.90 summary threshold is a separate operator judgment. Migration
    # 135 remains output-identical to the existing 0.50 RPC until that decision.
    assert "count(*) FILTER (WHERE ngf.confidence >= 0.50)" in flag_body
    assert "ngf.confidence >= 0.90" not in flag_body

    # Starting the final result at flag_agg intentionally omits active meetings
    # with zero qualifying flags, matching the existing RPC contract.
    assert "FROM flag_agg fa\n  LEFT JOIN item_agg ia" in flag_body


def test_future_public_policy_changes_redefine_both_definer_rpcs():
    """A tighter RLS policy must not be bypassed by stale definer bodies."""

    policy_tables = (
        "meetings",
        "agenda_items",
        "motions",
        "votes",
        "conflict_flags",
    )
    policy_pattern = re.compile(
        rf"(?:CREATE|ALTER)\s+POLICY\s+[^;]+?\s+ON\s+"
        rf"(?:public\.)?(?:{'|'.join(policy_tables)})\b",
        re.IGNORECASE,
    )
    baseline = "133_source_reconciliation_tombstones.sql"

    for migration in sorted((ROOT / "src" / "migrations").glob("*.sql")):
        if migration.name <= baseline:
            continue
        migration_sql = migration.read_text(encoding="utf-8")
        if not policy_pattern.search(migration_sql):
            continue

        prefix = int(re.match(r"^(\d+)", migration.name).group(1))
        assert prefix > 135, (
            f"{migration.name} changes a public policy consumed by migration "
            "135 but sorts before/at the definer rewrite. Give the policy "
            "migration a new prefix after 135 and redefine both RPCs there."
        )
        for function_name in (
            "public.get_meeting_flag_counts",
            "public.get_controversial_items",
        ):
            assert f"CREATE OR REPLACE FUNCTION {function_name}" in migration_sql, (
                f"{migration.name} changes public RLS used by {function_name} "
                "without updating the SECURITY DEFINER body in the same change."
            )
