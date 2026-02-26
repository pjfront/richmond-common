"""Tests for Sprint 2 migration SQL validity."""
import pathlib


MIGRATION_PATH = pathlib.Path(__file__).parent.parent / "src" / "migrations" / "006_sprint2_vote_intelligence.sql"


def test_migration_file_exists():
    assert MIGRATION_PATH.exists()


def test_migration_is_idempotent():
    """Migration should use IF NOT EXISTS and conditional updates."""
    sql = MIGRATION_PATH.read_text()
    # Bio columns use ADD COLUMN IF NOT EXISTS
    assert "IF NOT EXISTS" in sql or "ADD COLUMN IF NOT EXISTS" in sql
    # Backfill uses WHERE to avoid re-classifying
    assert "WHERE" in sql


def test_migration_backfills_appointments():
    """Migration should reclassify items to 'appointments'."""
    sql = MIGRATION_PATH.read_text().lower()
    assert "appointments" in sql
    assert "appoint" in sql  # keyword matching


def test_migration_adds_bio_columns():
    """Migration should add bio_factual, bio_summary, bio_generated_at, bio_model."""
    sql = MIGRATION_PATH.read_text()
    for col in ["bio_factual", "bio_summary", "bio_generated_at", "bio_model"]:
        assert col in sql, f"Missing column: {col}"
