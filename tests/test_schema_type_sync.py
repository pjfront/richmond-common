"""Static schema-type guards for the audit control-plane migrations.

The live database cannot be mutated until these migrations are committed, so
the generated Supabase type surface is mirrored in the same change and this
test prevents a partial schema/types rollout. Regenerate after applying the
committed migrations to replace the manual pre-deploy mirror byte-for-byte.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DB_TYPES = ROOT / "web" / "src" / "lib" / "database.types.ts"


def test_control_plane_migrations_are_reflected_in_database_types():
    text = DB_TYPES.read_text(encoding="utf-8")

    for table in (
        "source_change_jobs",
        "paper_filing_zero_results",
        "llm_cost_reservations",
        "lobbyist_document_extractions",
    ):
        assert f"      {table}: {{" in text

    for field in (
        "change_id: string | null",
        "dispatch_generation: number",
        "proceeding_classification_attempts: number",
        "proceeding_classification_claim_token: string | null",
        "prompt_version: string",
        "source_document_id: number | null",
    ):
        assert field in text

    for function in (
        "claim_due_source_change_jobs",
        "claim_source_change_job",
        "mark_source_change_base_completed",
        "retry_source_change_job",
        "continue_source_change_job",
        "complete_source_change_job",
        "reserve_llm_cost",
        "settle_llm_cost_reservation",
    ):
        assert f"      {function}: {{" in text
