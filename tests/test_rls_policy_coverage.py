"""Tests that every table created in migrations has a corresponding RLS read policy.

Root cause this prevents: Supabase enables RLS on all new tables by default.
If a migration creates a table but no "Public read" policy, the anonymous
frontend client gets zero rows with no error — silent data loss.

This test parses migration SQL files (no database connection needed) and
verifies that every CREATE TABLE has a matching CREATE POLICY ... FOR SELECT.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATIONS_DIR = Path(__file__).parent.parent / "src" / "migrations"

# Tables that intentionally have no public read policy.
# Add tables here ONLY with a comment explaining why.
EXEMPT_TABLES: set[str] = {
    "opencorporates_api_usage",  # Operational: rate limit tracking, not frontend-facing
}

# Regex patterns
CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?"
    r'"?(\w+)"?',
    re.IGNORECASE,
)
CREATE_POLICY_SELECT_RE = re.compile(
    r"CREATE\s+POLICY\s+.+?\s+ON\s+(?:public\.)?"
    r'"?(\w+)"?'
    r"\s+FOR\s+(?:SELECT|ALL)",
    re.IGNORECASE,
)


def _parse_migrations() -> tuple[set[str], set[str]]:
    """Parse all migration files and return (tables_created, tables_with_read_policy)."""
    tables_created: set[str] = set()
    tables_with_policy: set[str] = set()

    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        content = sql_file.read_text(encoding="utf-8")
        for match in CREATE_TABLE_RE.finditer(content):
            tables_created.add(match.group(1).lower())
        for match in CREATE_POLICY_SELECT_RE.finditer(content):
            tables_with_policy.add(match.group(1).lower())

    return tables_created, tables_with_policy


class TestRLSPolicyCoverage:
    """Every public table must have a SELECT policy to be visible to the frontend."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tables_created, self.tables_with_policy = _parse_migrations()

    def test_migrations_dir_exists(self):
        assert MIGRATIONS_DIR.exists(), f"Migrations dir not found: {MIGRATIONS_DIR}"

    def test_found_tables(self):
        assert len(self.tables_created) > 0, "No CREATE TABLE found in migrations"

    def test_found_policies(self):
        assert len(self.tables_with_policy) > 0, "No CREATE POLICY FOR SELECT found"

    def test_every_table_has_read_policy(self):
        """The core test: no table should be invisible to the frontend."""
        missing = self.tables_created - self.tables_with_policy - EXEMPT_TABLES
        if missing:
            sorted_missing = sorted(missing)
            msg = (
                f"{len(sorted_missing)} table(s) have no RLS SELECT policy "
                f"(invisible to frontend):\n"
            )
            for t in sorted_missing:
                msg += f"  - {t}\n"
            msg += (
                "\nFix: add a CREATE POLICY \"Public read\" ON {table} "
                "FOR SELECT USING (true); in the migration that creates the table, "
                "or in a backfill migration.\n"
                "If intentionally private, add to EXEMPT_TABLES in this test."
            )
            pytest.fail(msg)

    def test_exempt_tables_still_needed(self):
        """Keep EXEMPT_TABLES clean: remove entries that now have policies."""
        unnecessary = EXEMPT_TABLES & self.tables_with_policy
        if unnecessary:
            pytest.fail(
                f"Tables in EXEMPT_TABLES now have policies (remove from exempt): "
                f"{sorted(unnecessary)}"
            )
