"""Containment contract for the unvalidated influence-pattern taxonomy."""

from pathlib import Path


ROOT = Path(__file__).parents[1]
SOURCE = (
    ROOT
    / "src"
    / "migrations"
    / "136_restrict_unvalidated_influence_taxonomy.sql"
)
MIRROR = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260808013600_restrict_unvalidated_influence_taxonomy.sql"
)


def test_influence_taxonomy_containment_migration_is_mirrored_exactly():
    assert SOURCE.read_bytes() == MIRROR.read_bytes()


def test_unvalidated_taxonomy_is_operator_only():
    sql = SOURCE.read_text(encoding="utf-8")

    assert 'DROP POLICY IF EXISTS "Public read" ON public.influence_patterns;' in sql
    assert "FOR ALL\n    TO service_role" in sql

    for relation in (
        "public.influence_patterns",
        "public.v_influence_pattern_summary",
    ):
        assert (
            f"REVOKE ALL PRIVILEGES ON TABLE {relation}\n"
            "    FROM PUBLIC, anon, authenticated;"
        ) in sql

    assert (
        "REVOKE ALL PRIVILEGES ON SEQUENCE public.influence_patterns_id_seq\n"
        "    FROM PUBLIC, anon, authenticated;"
    ) in sql
    assert "GRANT SELECT ON TABLE public.influence_patterns TO service_role;" in sql
    assert (
        "GRANT SELECT ON TABLE public.v_influence_pattern_summary TO service_role;"
        in sql
    )


def test_containment_preserves_rows_and_view_definition():
    sql = SOURCE.read_text(encoding="utf-8").upper()

    assert "DELETE FROM" not in sql
    assert "TRUNCATE" not in sql
    assert "DROP VIEW" not in sql
    assert "CREATE OR REPLACE VIEW" not in sql
