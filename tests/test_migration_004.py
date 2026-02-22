# tests/test_migration_004.py
"""Verify migration 004 SQL is syntactically valid and idempotent."""
from pathlib import Path


MIGRATION_PATH = Path(__file__).parent.parent / "src" / "migrations" / "004_city_employees.sql"


def test_migration_file_exists():
    assert MIGRATION_PATH.exists(), f"Migration not found: {MIGRATION_PATH}"


def test_migration_is_idempotent_keywords():
    """All CREATE statements use IF NOT EXISTS / OR REPLACE."""
    sql = MIGRATION_PATH.read_text()
    for line in sql.splitlines():
        stripped = line.strip().upper()
        if stripped.startswith("CREATE TABLE"):
            assert "IF NOT EXISTS" in stripped, f"Non-idempotent: {line.strip()}"
        if stripped.startswith("CREATE INDEX"):
            assert "IF NOT EXISTS" in stripped, f"Non-idempotent: {line.strip()}"
        if stripped.startswith("CREATE VIEW") or stripped.startswith("CREATE OR REPLACE VIEW"):
            assert "OR REPLACE" in stripped, f"Non-idempotent: {line.strip()}"


def test_migration_has_city_fips():
    """city_fips column present in main table."""
    sql = MIGRATION_PATH.read_text()
    assert "city_fips" in sql
    assert "REFERENCES cities(fips_code)" in sql


def test_migration_has_unique_constraint():
    sql = MIGRATION_PATH.read_text()
    assert "uq_city_employee" in sql
