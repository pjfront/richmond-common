"""Schema-contract tests: verify that columns referenced in Python code
actually exist in the database.

These tests catch the class of bugs where code references a column name
that doesn't exist (e.g., `documents.extracted_text` when the real column
is `raw_text`). They query information_schema against the live Supabase
database, so they require DATABASE_URL to be set.

Skipped automatically in environments without DATABASE_URL (local dev
without .env, CI without secrets).
"""
import os
import pytest
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)


def _get_connection():
    """Get a database connection, or None if DATABASE_URL is not set."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return None
    import psycopg2
    return psycopg2.connect(database_url)


def _get_table_columns(conn, table_name: str) -> set[str]:
    """Query information_schema for column names of a table."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = %s""",
            (table_name,),
        )
        return {row[0] for row in cur.fetchall()}


# ── Column contracts ─────────────────────────────────────────
# Each entry maps a table to the columns that Python code references.
# If code is updated to use a new column, add it here.
# If a migration renames/removes a column, these tests will catch it.

SCHEMA_CONTRACTS = {
    "documents": {
        "id", "city_fips", "source_type", "source_url", "source_identifier",
        "raw_content", "raw_text", "content_hash", "mime_type",
        "credibility_tier", "metadata",
    },
    "conflict_flags": {
        "id", "city_fips", "meeting_id", "scan_run_id", "flag_type",
        "description", "evidence", "confidence", "scan_mode",
        "data_cutoff_date", "agenda_item_id", "official_id",
        "legal_reference", "publication_tier", "is_current",
        "confidence_factors", "scanner_version",
    },
    "pending_decisions": {
        "id", "city_fips", "decision_type", "severity", "title",
        "description", "source", "evidence", "entity_type", "entity_id",
        "link", "dedup_key", "status",
    },
    "meetings": {
        "id", "city_fips", "document_id", "meeting_date", "meeting_type",
        "call_to_order_time", "adjournment_time", "presiding_officer",
        "metadata",
    },
    "agenda_items": {
        "id", "meeting_id", "item_number", "title", "description",
        "department", "category", "is_consent_calendar",
        "was_pulled_from_consent",
    },
    "contributions": {
        "id", "donor_id", "committee_id", "amount", "contribution_date",
        "source", "filing_id",
    },
    "donors": {
        "id", "city_fips", "name", "normalized_name", "employer",
        "normalized_employer", "occupation",
    },
}


@pytest.fixture(scope="module")
def db_conn():
    """Database connection fixture. Skips if DATABASE_URL is not set or unreachable."""
    conn = _get_connection()
    if conn is None:
        pytest.skip("DATABASE_URL not set — skipping schema contract tests")
    # Verify the connection actually works (CI sets a fake DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:
        conn.close()
        pytest.skip("Database unreachable — skipping schema contract tests")
    yield conn
    conn.close()


@pytest.mark.parametrize("table_name,expected_columns", SCHEMA_CONTRACTS.items())
def test_table_has_required_columns(db_conn, table_name, expected_columns):
    """Verify that columns referenced in Python code exist in the database.

    This catches:
    - Code referencing a column that was renamed or removed by a migration
    - Code written against an assumed schema that was never migrated
    - Typos in column names in SQL strings
    """
    actual_columns = _get_table_columns(db_conn, table_name)
    assert actual_columns, f"Table '{table_name}' does not exist or has no columns"

    missing = expected_columns - actual_columns
    assert not missing, (
        f"Table '{table_name}' is missing columns referenced in Python code: "
        f"{sorted(missing)}. Actual columns: {sorted(actual_columns)}"
    )
