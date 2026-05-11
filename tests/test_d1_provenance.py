"""D1 provenance enforcement.

CLAUDE.md design principle D1 requires every API response that serves the
UI to include source_url, extracted_at, source_tier, and confidence_score
as non-nullable columns. The five-audit consolidation (2026-05-11) found
this principle was performative: ~11 of 103 migrations declared any
subset of these columns, almost never NOT NULL.

This test closes the gate going forward. It does NOT backfill existing
tables — that's Phase 4.x work. It DOES catch the next public-facing
table that ships without thinking about provenance.

Three enforcement layers:

1. queries.ts vs manifest sync. Every `.from('table')` in
   web/src/lib/queries.ts must appear in docs/d1-provenance-manifest.yaml.
   A new table in queries.ts without a manifest entry fails this test
   with a message asking the author to classify it (compliant /
   grandfathered / exempt). Grandfathered status is reserved for
   pre-existing tables — new tables must ship compliant or exempt with
   documented reason.

2. compliant tables verified. Every table marked `status: compliant`
   must have all four columns declared NOT NULL in the migration that
   defines it. Drift fails the test (forces an explicit demotion to
   grandfathered + a recorded gap).

3. grandfathered debt visible. Tables marked `grandfathered` are
   reported as known debt in test output but do not fail the build.
   The list shrinks over time as backfills land.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).parent.parent
_QUERIES_DIR = _ROOT / "web" / "src" / "lib" / "queries"
_QUERIES_TS_LEGACY = _ROOT / "web" / "src" / "lib" / "queries.ts"
_MANIFEST = _ROOT / "docs" / "d1-provenance-manifest.yaml"
_MIGRATIONS_DIR = _ROOT / "src" / "migrations"

D1_COLUMNS = ("source_url", "extracted_at", "source_tier", "confidence_score")


def _load_manifest() -> dict:
    with _MANIFEST.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _tables_from_queries_ts() -> set[str]:
    """Extract the set of public tables referenced from the queries module.

    Phase 2.4: queries.ts is split into web/src/lib/queries/{domain}.ts.
    Scans every .ts file in that directory plus the legacy single-file path.
    """
    tables: set[str] = set()
    pattern = re.compile(r"\.from\(['\"]([a-z_][a-z0-9_]*)['\"]")
    candidates = []
    if _QUERIES_TS_LEGACY.exists():
        candidates.append(_QUERIES_TS_LEGACY)
    if _QUERIES_DIR.exists():
        candidates.extend(_QUERIES_DIR.glob("*.ts"))
    for path in candidates:
        tables.update(pattern.findall(path.read_text(encoding="utf-8")))
    return tables


def _find_table_definition(table: str) -> str | None:
    """Concatenate all CREATE TABLE / ALTER TABLE statements touching a
    table. Returned as one blob so a single regex sweep can check column
    declarations whether they came in via the original CREATE or a later
    ALTER ADD COLUMN.
    """
    blob_parts: list[str] = []
    create_pattern = re.compile(
        rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?{re.escape(table)}\s*\((.*?)\);",
        re.IGNORECASE | re.DOTALL,
    )
    alter_pattern = re.compile(
        rf"ALTER\s+TABLE\s+(?:public\.)?{re.escape(table)}\s+(.*?);",
        re.IGNORECASE | re.DOTALL,
    )
    for migration in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        text = migration.read_text(encoding="utf-8")
        for m in create_pattern.finditer(text):
            blob_parts.append(m.group(1))
        for m in alter_pattern.finditer(text):
            blob_parts.append(m.group(1))
    return "\n".join(blob_parts) if blob_parts else None


def _column_is_not_null(blob: str, column: str) -> bool:
    """Heuristic: column appears in a definition with NOT NULL nearby
    (within ~80 chars on the same line)."""
    for line in blob.splitlines():
        if re.search(rf"\b{re.escape(column)}\b", line):
            if re.search(r"\bNOT\s+NULL\b", line, re.IGNORECASE):
                return True
    return False


def test_queries_ts_tables_match_manifest():
    """Layer 1: queries.ts and the manifest agree on the set of public tables.

    If this fails, the queries.ts side has changed without the manifest
    being updated. Add the new table to docs/d1-provenance-manifest.yaml
    with one of: compliant (preferred for new tables), grandfathered
    (NOT allowed for new tables — reserved for pre-2026-05-11 entries),
    exempt (with reason).
    """
    manifest = _load_manifest()
    manifest_tables = set(manifest["tables"].keys())
    queries_tables = _tables_from_queries_ts()

    missing_from_manifest = queries_tables - manifest_tables
    missing_from_queries = manifest_tables - queries_tables

    assert not missing_from_manifest, (
        f"Tables referenced in queries.ts but not in d1-provenance-manifest.yaml: "
        f"{sorted(missing_from_manifest)}. Add them to the manifest with a "
        f"status (compliant/grandfathered/exempt) before merging."
    )
    assert not missing_from_queries, (
        f"Tables in d1-provenance-manifest.yaml but no longer referenced in "
        f"queries.ts: {sorted(missing_from_queries)}. Remove them from the "
        f"manifest or restore the queries.ts reference."
    )


def test_compliant_tables_actually_compliant():
    """Layer 2: tables marked compliant have all four columns NOT NULL.

    Drift means someone promoted a table to compliant without the columns
    actually being declared, or a later migration weakened a constraint.
    Either way, the manifest no longer reflects reality and must be fixed.
    """
    manifest = _load_manifest()
    failures: list[str] = []
    for table, entry in manifest["tables"].items():
        if entry.get("status") != "compliant":
            continue
        blob = _find_table_definition(table)
        if blob is None:
            failures.append(f"  {table}: marked compliant but no CREATE TABLE found in src/migrations/")
            continue
        missing = [c for c in D1_COLUMNS if not _column_is_not_null(blob, c)]
        if missing:
            failures.append(f"  {table}: missing NOT NULL on {missing}")
    assert not failures, (
        "Tables marked `compliant` in d1-provenance-manifest.yaml do not "
        "actually have the D1 quartet declared NOT NULL:\n"
        + "\n".join(failures)
        + "\n\nDemote to `grandfathered` with the gap recorded, or ship a "
        "migration that adds the NOT NULL constraints."
    )


def test_grandfathered_debt_summary(capsys):
    """Informational: prints the grandfathered debt list. Always passes.

    Run via `pytest tests/test_d1_provenance.py::test_grandfathered_debt_summary -s`
    to see the current backlog. The summary is also useful in CI logs as a
    standing reminder of how much D1 backfill work remains.
    """
    manifest = _load_manifest()
    grandfathered = {
        table: entry
        for table, entry in manifest["tables"].items()
        if entry.get("status") == "grandfathered"
    }
    if not grandfathered:
        print("\nD1 grandfathered backlog: empty. All public tables are compliant or exempt.")
        return
    print(f"\nD1 grandfathered backlog: {len(grandfathered)} table(s)")
    for table, entry in sorted(grandfathered.items()):
        missing = entry.get("missing", ["all four"])
        print(f"  - {table}: missing {missing}")


def test_no_new_grandfathered_entries():
    """Guard against backsliding.

    `grandfathered` status is reserved for pre-2026-05-11 entries. New
    tables added to the manifest must be `compliant` or `exempt`.
    Adding new grandfathered entries silently expands the backlog.

    If you genuinely need a new grandfathered entry (e.g., importing
    legacy data that can't be backfilled in the same PR), update this
    test's allowlist with a reason — that's the explicit acknowledgment.
    """
    # Snapshot of grandfathered tables as of 2026-05-11. Adding to this
    # list requires a code change reviewers will see.
    allowed_grandfathered = {
        "agenda_items", "behested_payments", "bodies", "closed_session_items",
        "comment_theme_assignments", "commission_members", "commissions",
        "committees", "conflict_flags", "contributions", "donors",
        "economic_interests", "election_candidates", "elections",
        "filing_period_briefings", "independent_expenditures",
        "item_theme_narratives", "meeting_attendance", "meetings",
        "motions", "neighborhood_councils", "nextrequest_requests",
        "officials", "public_comments", "votes",
    }
    manifest = _load_manifest()
    actual_grandfathered = {
        table for table, entry in manifest["tables"].items()
        if entry.get("status") == "grandfathered"
    }
    new_grandfathered = actual_grandfathered - allowed_grandfathered
    assert not new_grandfathered, (
        f"New tables marked `grandfathered`: {sorted(new_grandfathered)}. "
        f"New tables must ship `compliant` (with NOT NULL provenance columns) "
        f"or `exempt` (with a documented reason). If genuinely necessary, "
        f"add to the allowlist in tests/test_d1_provenance.py with a comment "
        f"explaining why."
    )
    removed = allowed_grandfathered - actual_grandfathered
    if removed:
        # Backlog shrinking is good — update the allowlist to lock it in.
        # We don't fail on this; we just print a celebratory note.
        print(f"\nD1 backlog shrunk: {sorted(removed)} no longer grandfathered. "
              f"Update allowed_grandfathered in this test to lock the win.")
