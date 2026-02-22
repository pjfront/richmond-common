# City Leadership & Top Employees — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ingest city employee payroll data from Socrata, classify organizational hierarchy via title keywords, and store in a `city_employees` table with ground truth validation.

**Architecture:** Socrata-first with zero Claude API cost. The `payroll_ingester.py` module fetches structured payroll data via the existing `socrata_client.py`, normalizes names (reusing `db.py`'s `_normalize_name` pattern), classifies hierarchy levels via title keyword matching, and loads to Supabase. Ground truth in `officials.json` validates the heuristic output.

**Tech Stack:** Python, Socrata SODA API (via `sodapy`), PostgreSQL (Supabase), pytest

**Design doc:** `docs/plans/2026-02-22-city-leadership-design.md`

**Migration number:** 004 (assigned — commissions gets 005)

**Branch:** `feature/city-leadership`

---

## Pre-flight: Discover Socrata Payroll Schema

Before writing any code, run this to confirm exact column names:

```bash
cd src && python socrata_client.py payroll --list-columns
```

This reveals the actual field names in Richmond's payroll dataset (`crbs-mam9`). The plan uses placeholder names (`employeename`, `jobtitle`, `department`, `annualsalary`, `totalcompensation`, `fiscalyear`) — **replace these with the real column names from the output before implementing.**

Also fetch a sample row to see data shapes:

```bash
cd src && python socrata_client.py payroll --limit 3
```

---

### Task 1: Migration — `city_employees` Table

**Files:**
- Create: `src/migrations/004_city_employees.sql`
- Test: `tests/test_migration_004.py`

**Step 1: Write the migration file**

```sql
-- Migration 004: City employees & leadership hierarchy
-- Ingests payroll data from Socrata, classifies org hierarchy by title.
-- Idempotent: safe to re-run (uses IF NOT EXISTS).

-- ============================================================
-- New Table: city_employees
-- Employee payroll records with inferred org hierarchy.
-- ============================================================

CREATE TABLE IF NOT EXISTS city_employees (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    name VARCHAR(300) NOT NULL,
    normalized_name VARCHAR(300) NOT NULL,
    job_title VARCHAR(300),
    department VARCHAR(200),
    is_department_head BOOLEAN NOT NULL DEFAULT FALSE,
    hierarchy_level SMALLINT NOT NULL DEFAULT 0,
    annual_salary NUMERIC,
    total_compensation NUMERIC,
    fiscal_year VARCHAR(4),
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    source VARCHAR(50) NOT NULL DEFAULT 'socrata_payroll',
    socrata_record_id VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_city_employee UNIQUE (city_fips, normalized_name, department, fiscal_year)
);

CREATE INDEX IF NOT EXISTS idx_city_employees_fips ON city_employees(city_fips);
CREATE INDEX IF NOT EXISTS idx_city_employees_current ON city_employees(is_current, city_fips);
CREATE INDEX IF NOT EXISTS idx_city_employees_dept ON city_employees(department);
CREATE INDEX IF NOT EXISTS idx_city_employees_name ON city_employees(normalized_name);
CREATE INDEX IF NOT EXISTS idx_city_employees_hierarchy ON city_employees(hierarchy_level, city_fips);
CREATE INDEX IF NOT EXISTS idx_city_employees_salary ON city_employees(annual_salary DESC);

-- ============================================================
-- View: v_staff_agenda_context
-- Joins agenda items to department heads for staff context.
-- ============================================================

CREATE OR REPLACE VIEW v_staff_agenda_context AS
SELECT
    ai.id AS agenda_item_id,
    ai.title AS item_title,
    ai.department AS item_department,
    m.meeting_date,
    m.city_fips,
    ce.name AS dept_head_name,
    ce.job_title AS dept_head_title,
    ce.department AS employee_department,
    ce.annual_salary,
    ce.hierarchy_level
FROM agenda_items ai
JOIN meetings m ON ai.meeting_id = m.id
LEFT JOIN city_employees ce
    ON m.city_fips = ce.city_fips
    AND ce.is_current = TRUE
    AND ce.is_department_head = TRUE
    AND LOWER(ai.department) = LOWER(ce.department)
WHERE ai.department IS NOT NULL;
```

**Step 2: Write the migration test**

```python
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
```

**Step 3: Run tests to verify they pass**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP && python3 -m pytest tests/test_migration_004.py -v
```

Expected: 4 PASSED

**Step 4: Commit**

```bash
git add src/migrations/004_city_employees.sql tests/test_migration_004.py
git commit -m "feat: add migration 004 for city_employees table and v_staff_agenda_context view"
```

---

### Task 2: Hierarchy Classifier Module

**Files:**
- Create: `src/hierarchy_classifier.py`
- Test: `tests/test_hierarchy_classifier.py`

**Step 1: Write failing tests**

```python
# tests/test_hierarchy_classifier.py
"""Tests for title-based hierarchy classification."""
from hierarchy_classifier import classify_title, LEVEL_LABELS


class TestClassifyTitle:
    """Hierarchy level 1-4 inference from job titles."""

    def test_city_manager(self):
        level, is_head = classify_title("City Manager")
        assert level == 1
        assert is_head is True

    def test_city_attorney(self):
        level, is_head = classify_title("City Attorney")
        assert level == 1
        assert is_head is True

    def test_city_clerk(self):
        level, is_head = classify_title("City Clerk")
        assert level == 1
        assert is_head is True

    def test_director(self):
        level, is_head = classify_title("Director of Public Works")
        assert level == 2
        assert is_head is True

    def test_fire_chief(self):
        level, is_head = classify_title("Fire Chief")
        assert level == 2
        assert is_head is True

    def test_police_chief(self):
        level, is_head = classify_title("Chief of Police")
        assert level == 2
        assert is_head is True

    def test_city_engineer(self):
        level, is_head = classify_title("City Engineer")
        assert level == 2
        assert is_head is True

    def test_assistant_director(self):
        level, is_head = classify_title("Assistant Director of Finance")
        assert level == 3
        assert is_head is False

    def test_deputy_director(self):
        level, is_head = classify_title("Deputy Director")
        assert level == 3
        assert is_head is False

    def test_division_manager(self):
        level, is_head = classify_title("Division Manager - Planning")
        assert level == 3
        assert is_head is False

    def test_supervisor(self):
        level, is_head = classify_title("Maintenance Supervisor")
        assert level == 4
        assert is_head is False

    def test_senior_manager(self):
        level, is_head = classify_title("Senior Manager of IT Services")
        assert level == 4
        assert is_head is False

    def test_principal_planner(self):
        level, is_head = classify_title("Principal Planner")
        assert level == 4
        assert is_head is False

    def test_regular_employee(self):
        level, is_head = classify_title("Administrative Assistant II")
        assert level == 0
        assert is_head is False

    def test_empty_title(self):
        level, is_head = classify_title("")
        assert level == 0
        assert is_head is False

    def test_none_title(self):
        level, is_head = classify_title(None)
        assert level == 0
        assert is_head is False

    def test_case_insensitive(self):
        level, _ = classify_title("CITY MANAGER")
        assert level == 1

    def test_assistant_not_promoted_to_director(self):
        """'Assistant to the City Manager' should NOT be level 1."""
        level, is_head = classify_title("Assistant to the City Manager")
        assert level == 3
        assert is_head is False

    def test_level_labels(self):
        assert LEVEL_LABELS[0] == "Unclassified"
        assert LEVEL_LABELS[1] == "Executive"
        assert len(LEVEL_LABELS) == 5


class TestEdgeCases:
    """Titles that could trip up naive matching."""

    def test_chief_financial_officer(self):
        level, is_head = classify_title("Chief Financial Officer")
        assert level == 2
        assert is_head is True

    def test_engineering_technician(self):
        """'Engineer' in title but not 'City Engineer'."""
        level, is_head = classify_title("Engineering Technician")
        assert level == 0
        assert is_head is False

    def test_police_sergeant(self):
        """Sergeant has 'police' context but is not Chief."""
        level, is_head = classify_title("Police Sergeant")
        assert level == 0
        assert is_head is False
```

**Step 2: Run tests — expect FAIL**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP && python3 -m pytest tests/test_hierarchy_classifier.py -v
```

Expected: ModuleNotFoundError for `hierarchy_classifier`

**Step 3: Implement the classifier**

```python
# src/hierarchy_classifier.py
"""Title-based hierarchy classification for city employees.

Uses keyword pattern matching to infer organizational hierarchy
from job titles. Zero LLM cost — structured data + heuristics.

Levels:
    1 = Executive (City Manager, City Attorney, City Clerk)
    2 = Department Head (Director, Chief, City Engineer)
    3 = Senior Management (Assistant/Deputy Director, Division Manager)
    4 = Mid-Management (Supervisor, Senior Manager, Principal)
    0 = Unclassified (all other employees)
"""
from __future__ import annotations

import re

LEVEL_LABELS = {
    0: "Unclassified",
    1: "Executive",
    2: "Department Head",
    3: "Senior Management",
    4: "Mid-Management",
}

# Order matters: check level 3 (assistant/deputy) BEFORE level 2 (director/chief)
# so "Assistant Director" doesn't match "Director" first.
_LEVEL_3_PATTERNS = [
    r"\bassistant\s+(city\s+manager|director|chief)\b",
    r"\bassistant\s+to\s+the\b",
    r"\bdeputy\s+(director|chief|city)\b",
    r"\bdivision\s+manager\b",
]

_LEVEL_1_PATTERNS = [
    r"\bcity\s+manager\b",
    r"\bcity\s+attorney\b",
    r"\bcity\s+clerk\b",
]

_LEVEL_2_PATTERNS = [
    r"\bdirector\b",
    r"\bchief\b",
    r"\bcity\s+engineer\b",
]

_LEVEL_4_PATTERNS = [
    r"\bsupervisor\b",
    r"\bsenior\s+manager\b",
    r"\bprincipal\s+(planner|analyst|engineer|accountant)\b",
]


def classify_title(title: str | None) -> tuple[int, bool]:
    """Classify a job title into hierarchy level and department head status.

    Returns:
        (hierarchy_level, is_department_head) tuple.
        Levels 1-2 are department heads. Level 0 is unclassified.
    """
    if not title:
        return 0, False

    t = title.lower().strip()

    # Check level 3 FIRST — "assistant director" should not match "director"
    for pattern in _LEVEL_3_PATTERNS:
        if re.search(pattern, t):
            return 3, False

    for pattern in _LEVEL_1_PATTERNS:
        if re.search(pattern, t):
            return 1, True

    for pattern in _LEVEL_2_PATTERNS:
        if re.search(pattern, t):
            return 2, True

    for pattern in _LEVEL_4_PATTERNS:
        if re.search(pattern, t):
            return 4, False

    return 0, False
```

**Step 4: Run tests — expect PASS**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP && python3 -m pytest tests/test_hierarchy_classifier.py -v
```

Expected: All PASSED

**Step 5: Commit**

```bash
git add src/hierarchy_classifier.py tests/test_hierarchy_classifier.py
git commit -m "feat: add title-based hierarchy classifier for city employees"
```

---

### Task 3: Payroll Ingester — Core Logic

**Files:**
- Create: `src/payroll_ingester.py`
- Test: `tests/test_payroll_ingester.py`

**Step 1: Write failing tests**

```python
# tests/test_payroll_ingester.py
"""Tests for Socrata payroll ingestion pipeline."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from payroll_ingester import (
    parse_payroll_records,
    normalize_employee,
    build_employee_record,
    CITY_FIPS,
)


# ── Sample Socrata row (adjust field names after pre-flight) ──

SAMPLE_ROW = {
    "employeename": "Shasa Curl",
    "jobtitle": "City Manager",
    "department": "City Manager's Office",
    "annualsalary": "350000",
    "totalcompensation": "420000",
    "fiscalyear": "2026",
}

SAMPLE_ROW_REGULAR = {
    "employeename": "Jane Doe",
    "jobtitle": "Administrative Assistant II",
    "department": "Finance",
    "annualsalary": "55000",
    "totalcompensation": "68000",
    "fiscalyear": "2026",
}


class TestNormalizeEmployee:
    def test_basic_normalization(self):
        rec = normalize_employee(SAMPLE_ROW)
        assert rec["name"] == "Shasa Curl"
        assert rec["normalized_name"] == "shasa curl"
        assert rec["job_title"] == "City Manager"

    def test_strips_whitespace(self):
        row = {**SAMPLE_ROW, "employeename": "  John   Smith  "}
        rec = normalize_employee(row)
        assert rec["name"] == "John Smith"
        assert rec["normalized_name"] == "john smith"

    def test_salary_parsing(self):
        rec = normalize_employee(SAMPLE_ROW)
        assert rec["annual_salary"] == 350000.0
        assert rec["total_compensation"] == 420000.0

    def test_missing_salary(self):
        row = {**SAMPLE_ROW, "annualsalary": None}
        rec = normalize_employee(row)
        assert rec["annual_salary"] is None


class TestBuildEmployeeRecord:
    def test_city_manager_classified(self):
        rec = build_employee_record(SAMPLE_ROW, city_fips=CITY_FIPS)
        assert rec["hierarchy_level"] == 1
        assert rec["is_department_head"] is True
        assert rec["city_fips"] == CITY_FIPS

    def test_regular_employee_unclassified(self):
        rec = build_employee_record(SAMPLE_ROW_REGULAR, city_fips=CITY_FIPS)
        assert rec["hierarchy_level"] == 0
        assert rec["is_department_head"] is False

    def test_source_field(self):
        rec = build_employee_record(SAMPLE_ROW, city_fips=CITY_FIPS)
        assert rec["source"] == "socrata_payroll"


class TestParsePayrollRecords:
    def test_batch_parsing(self):
        rows = [SAMPLE_ROW, SAMPLE_ROW_REGULAR]
        records = parse_payroll_records(rows, city_fips=CITY_FIPS)
        assert len(records) == 2
        assert records[0]["hierarchy_level"] == 1
        assert records[1]["hierarchy_level"] == 0

    def test_stats_summary(self):
        rows = [SAMPLE_ROW, SAMPLE_ROW_REGULAR]
        records = parse_payroll_records(rows, city_fips=CITY_FIPS)
        heads = [r for r in records if r["is_department_head"]]
        assert len(heads) == 1

    def test_empty_input(self):
        records = parse_payroll_records([], city_fips=CITY_FIPS)
        assert records == []

    def test_skips_empty_names(self):
        row = {**SAMPLE_ROW, "employeename": ""}
        records = parse_payroll_records([row], city_fips=CITY_FIPS)
        assert len(records) == 0
```

> **NOTE:** The field names (`employeename`, `jobtitle`, `department`, `annualsalary`, `totalcompensation`, `fiscalyear`) are placeholders. After the pre-flight step, replace these throughout the test file AND the implementation with the actual Socrata column names.

**Step 2: Run tests — expect FAIL**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP && python3 -m pytest tests/test_payroll_ingester.py -v
```

Expected: ModuleNotFoundError for `payroll_ingester`

**Step 3: Implement the ingester core**

```python
# src/payroll_ingester.py
"""
Socrata payroll ingester for city employee hierarchy.

Fetches payroll data from Transparent Richmond (Socrata), normalizes names,
classifies hierarchy by title keywords, and stores in city_employees table.

Usage:
    python payroll_ingester.py --fiscal-year 2026 --stats
    python payroll_ingester.py --fiscal-year 2026 --output employees.json
    python payroll_ingester.py --fiscal-year 2026 --load
    python payroll_ingester.py --list-departments
    python payroll_ingester.py --validate-ground-truth
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from hierarchy_classifier import classify_title, LEVEL_LABELS  # noqa: E402

logger = logging.getLogger(__name__)

CITY_FIPS = "0660620"

# ── Socrata field mapping ──────────────────────────────────────
# IMPORTANT: Update these after running `python socrata_client.py payroll --list-columns`
FIELD_MAP = {
    "name": "employeename",
    "title": "jobtitle",
    "department": "department",
    "salary": "annualsalary",
    "total_comp": "totalcompensation",
    "fiscal_year": "fiscalyear",
}


def _safe_float(val: Any) -> float | None:
    """Parse a numeric value, returning None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _normalize_name(name: str) -> str:
    """Lowercase and collapse whitespace for matching."""
    return " ".join(name.lower().split())


def normalize_employee(row: dict) -> dict:
    """Extract and normalize fields from a Socrata payroll row."""
    raw_name = (row.get(FIELD_MAP["name"]) or "").strip()
    name = " ".join(raw_name.split())  # collapse internal whitespace
    return {
        "name": name,
        "normalized_name": _normalize_name(name) if name else "",
        "job_title": (row.get(FIELD_MAP["title"]) or "").strip(),
        "department": (row.get(FIELD_MAP["department"]) or "").strip(),
        "annual_salary": _safe_float(row.get(FIELD_MAP["salary"])),
        "total_compensation": _safe_float(row.get(FIELD_MAP["total_comp"])),
        "fiscal_year": (row.get(FIELD_MAP["fiscal_year"]) or "").strip(),
    }


def build_employee_record(row: dict, *, city_fips: str = CITY_FIPS) -> dict:
    """Build a complete employee record with hierarchy classification."""
    emp = normalize_employee(row)
    level, is_head = classify_title(emp["job_title"])
    return {
        **emp,
        "city_fips": city_fips,
        "hierarchy_level": level,
        "is_department_head": is_head,
        "source": "socrata_payroll",
        "is_current": True,
    }


def parse_payroll_records(
    rows: list[dict], *, city_fips: str = CITY_FIPS
) -> list[dict]:
    """Parse a batch of Socrata payroll rows into employee records.

    Skips rows with empty names.
    """
    records = []
    for row in rows:
        rec = build_employee_record(row, city_fips=city_fips)
        if not rec["name"]:
            continue
        records.append(rec)
    return records


def fetch_payroll(
    fiscal_year: str, *, city_fips: str | None = None, limit: int = 50000
) -> list[dict]:
    """Fetch payroll records from Socrata for a given fiscal year."""
    from socrata_client import query_dataset

    fips = city_fips or CITY_FIPS
    fy_field = FIELD_MAP["fiscal_year"]
    return query_dataset(
        "payroll",
        where=f"{fy_field} = '{fiscal_year}'",
        limit=limit,
        city_fips=fips,
    )


def print_stats(records: list[dict]) -> None:
    """Print summary statistics for parsed employee records."""
    if not records:
        print("No records to summarize.")
        return

    total = len(records)
    by_level = {}
    for r in records:
        lvl = r["hierarchy_level"]
        by_level.setdefault(lvl, []).append(r)

    depts = sorted(set(r["department"] for r in records if r["department"]))

    print(f"\n{'='*60}")
    print(f" City Employee Payroll Summary")
    print(f"{'='*60}")
    print(f" Total employees: {total}")
    print(f" Departments:     {len(depts)}")
    print()
    for lvl in sorted(by_level.keys()):
        label = LEVEL_LABELS.get(lvl, f"Level {lvl}")
        count = len(by_level[lvl])
        print(f"  Level {lvl} ({label}): {count}")
    print()

    heads = [r for r in records if r["is_department_head"]]
    if heads:
        print(f" Department Heads ({len(heads)}):")
        for h in sorted(heads, key=lambda x: x["hierarchy_level"]):
            sal = f"${h['annual_salary']:,.0f}" if h["annual_salary"] else "N/A"
            print(f"   [{h['hierarchy_level']}] {h['name']:30s} {h['job_title']:35s} {sal}")
    print()


def validate_ground_truth(records: list[dict]) -> None:
    """Compare ingested records against ground truth in officials.json.

    HUMAN CHECKPOINT: Prints a quick-scan table showing matches and mismatches.
    Designed for <2 min review — just confirm the right people are flagged.
    """
    gt_path = Path(__file__).parent / "ground_truth" / "officials.json"
    if not gt_path.exists():
        print("No ground truth file found. Skipping validation.")
        return

    gt = json.loads(gt_path.read_text())
    leadership = gt.get("city_leadership", [])
    if not leadership:
        print("No city_leadership section in officials.json. Skipping validation.")
        return

    heads = {_normalize_name(r["name"]): r for r in records if r["is_department_head"]}

    print(f"\n{'='*60}")
    print(f" Ground Truth Validation ({len(leadership)} entries)")
    print(f"{'='*60}")
    matched = 0
    for gt_entry in leadership:
        gt_name = _normalize_name(gt_entry["name"])
        gt_level = gt_entry.get("hierarchy_level", "?")
        if gt_name in heads:
            rec = heads[gt_name]
            level_match = "OK" if rec["hierarchy_level"] == gt_level else f"MISMATCH (got {rec['hierarchy_level']})"
            print(f"  [FOUND]   {gt_entry['name']:30s} level={gt_level} {level_match}")
            matched += 1
        else:
            print(f"  [MISSING] {gt_entry['name']:30s} (not in payroll as dept head)")

    # Check for unexpected heads not in ground truth
    gt_names = {_normalize_name(e["name"]) for e in leadership}
    unexpected = [h for name, h in heads.items() if name not in gt_names and h["hierarchy_level"] <= 2]
    if unexpected:
        print(f"\n  Heads in payroll but NOT in ground truth ({len(unexpected)}):")
        for u in unexpected:
            print(f"  [EXTRA]   {u['name']:30s} {u['job_title']}")

    print(f"\n  Summary: {matched}/{len(leadership)} ground truth entries matched")
    print()


# ── CLI ─────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest city employee payroll from Socrata"
    )
    parser.add_argument("--fiscal-year", default="2026", help="Fiscal year to fetch")
    parser.add_argument("--stats", action="store_true", help="Print summary statistics")
    parser.add_argument("--output", type=Path, help="Save parsed JSON to file")
    parser.add_argument("--load", action="store_true", help="Load to Supabase")
    parser.add_argument("--list-departments", action="store_true", help="List departments")
    parser.add_argument("--validate-ground-truth", action="store_true", help="Compare against officials.json")
    parser.add_argument("--city-fips", default=None, help="City FIPS code (default: Richmond)")
    args = parser.parse_args()

    fips = args.city_fips or CITY_FIPS
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    logger.info("Fetching payroll for fiscal year %s ...", args.fiscal_year)
    raw_rows = fetch_payroll(args.fiscal_year, city_fips=fips)
    logger.info("Fetched %d raw rows from Socrata", len(raw_rows))

    records = parse_payroll_records(raw_rows, city_fips=fips)
    logger.info("Parsed %d employee records", len(records))

    if args.stats or (not args.output and not args.load):
        print_stats(records)

    if args.list_departments:
        depts = sorted(set(r["department"] for r in records if r["department"]))
        print(f"\nDepartments ({len(depts)}):")
        for d in depts:
            count = sum(1 for r in records if r["department"] == d)
            print(f"  {d} ({count} employees)")

    if args.validate_ground_truth:
        validate_ground_truth(records)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(records, indent=2, default=str))
        logger.info("Saved %d records to %s", len(records), args.output)

    if args.load:
        load_to_db(records, city_fips=fips)


def load_to_db(records: list[dict], *, city_fips: str = CITY_FIPS) -> None:
    """Load employee records to Supabase city_employees table."""
    from db import get_connection

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            loaded = 0
            for rec in records:
                cur.execute(
                    """INSERT INTO city_employees
                       (city_fips, name, normalized_name, job_title, department,
                        is_department_head, hierarchy_level, annual_salary,
                        total_compensation, fiscal_year, is_current, source)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT ON CONSTRAINT uq_city_employee
                       DO UPDATE SET
                           job_title = EXCLUDED.job_title,
                           is_department_head = EXCLUDED.is_department_head,
                           hierarchy_level = EXCLUDED.hierarchy_level,
                           annual_salary = EXCLUDED.annual_salary,
                           total_compensation = EXCLUDED.total_compensation,
                           is_current = EXCLUDED.is_current,
                           source = EXCLUDED.source,
                           updated_at = NOW()""",
                    (
                        rec["city_fips"], rec["name"], rec["normalized_name"],
                        rec["job_title"], rec["department"],
                        rec["is_department_head"], rec["hierarchy_level"],
                        rec["annual_salary"], rec["total_compensation"],
                        rec["fiscal_year"], rec["is_current"], rec["source"],
                    ),
                )
                loaded += 1
                if loaded % 500 == 0:
                    conn.commit()
                    logger.info("  loaded %d / %d ...", loaded, len(records))
            conn.commit()
        logger.info("Loaded %d employee records to database", loaded)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

**Step 4: Run tests — expect PASS**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP && python3 -m pytest tests/test_payroll_ingester.py -v
```

Expected: All PASSED

**Step 5: Commit**

```bash
git add src/payroll_ingester.py tests/test_payroll_ingester.py
git commit -m "feat: add payroll ingester with Socrata fetch, hierarchy classification, and DB loading"
```

---

### Task 4: Ground Truth Seeding (Human Checkpoint)

**Files:**
- Modify: `src/ground_truth/officials.json`

**This is a human task.** The system pre-generates context to minimize decision time.

**Step 1: Generate candidate list from payroll data**

```bash
cd src && python payroll_ingester.py --fiscal-year 2026 --stats
```

This prints all department heads found by the classifier. The human reviews this output and picks the ~15-20 correct entries.

**Step 2: Cross-reference against city website**

Open `https://www.ci.richmond.ca.us/Directory.aspx` and verify names/titles.

**Step 3: Add `city_leadership` section to `officials.json`**

The human adds entries in this format (pre-filled template below — just edit names/titles):

```json
{
  "city_fips": "0660620",
  "city_name": "Richmond, California",
  "updated": "2026-02-22",
  "current_council_members": [ ... ],
  "former_council_members": [ ... ],
  "city_leadership": [
    {
      "name": "Shasa Curl",
      "title": "City Manager",
      "department": "City Manager's Office",
      "hierarchy_level": 1,
      "notes": "Appointed 2021"
    }
  ]
}
```

**Step 4: Validate ground truth against payroll output**

```bash
cd src && python payroll_ingester.py --fiscal-year 2026 --validate-ground-truth
```

This prints a match/mismatch table designed for <2 min review. Check that:
- All ground truth entries are FOUND in payroll
- No hierarchy level MISMATCH
- Any EXTRA heads in payroll that aren't in ground truth are expected

**Step 5: Commit**

```bash
git add src/ground_truth/officials.json
git commit -m "feat: seed city leadership ground truth in officials.json"
```

---

### Task 5: Update Migration Health Check

**Files:**
- Modify: `web/src/app/api/health/route.ts` (add `004_city_employees` to migration groups)
- Modify: `src/staleness_monitor.py` (add `city_employees` to schema health check)

**Step 1: Find the migration groups in the health endpoint**

The health check probes tables per migration group. Add:

```typescript
"004_city_employees": ["city_employees"],
```

**Step 2: Add `city_employees` to `staleness_monitor.py`'s `check_schema_health()`**

Add `"city_employees"` to the table list it probes.

**Step 3: Run existing health check tests**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP && python3 -m pytest tests/ -k "health" -v
```

Expected: PASS (existing tests shouldn't break; new table is additive)

**Step 4: Commit**

```bash
git add web/src/app/api/health/route.ts src/staleness_monitor.py
git commit -m "feat: add city_employees to migration health check"
```

---

### Task 6: End-to-End Integration Test

**Step 1: Run the full payroll pipeline against real Socrata data**

```bash
cd src && python payroll_ingester.py --fiscal-year 2026 --stats --output ../data/employees_2026.json
```

**Step 2: Verify output JSON**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP && python3 -c "
import json
data = json.loads(open('data/employees_2026.json').read())
print(f'Total: {len(data)}')
heads = [d for d in data if d['is_department_head']]
print(f'Department heads: {len(heads)}')
for h in sorted(heads, key=lambda x: x['hierarchy_level']):
    print(f'  [{h[\"hierarchy_level\"]}] {h[\"name\"]:30s} {h[\"job_title\"]}')
"
```

Expected: ~15-25 department heads identified across levels 1-2.

**Step 3: Run full test suite**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP && python3 -m pytest tests/ -v --tb=short
```

Expected: All tests PASS (existing 340 + new tests)

**Step 4: Commit output data (optional — depends on whether we track payroll JSON in repo)**

The JSON output is derived data. Decision: **do NOT commit** `data/employees_2026.json` to the repo — it's generated from Socrata and can be re-fetched. Add to `.gitignore` if needed.

---

### Task 7: Final Commit + Summary

**Step 1: Verify all files are committed**

```bash
git status
git log --oneline -10
```

**Step 2: Run full test suite one final time**

```bash
cd /Users/phillip.front/Projects/MyProjects/RTP && python3 -m pytest tests/ -v --tb=short
```

**New files created:**
- `src/migrations/004_city_employees.sql`
- `src/hierarchy_classifier.py`
- `src/payroll_ingester.py`
- `tests/test_migration_004.py`
- `tests/test_hierarchy_classifier.py`
- `tests/test_payroll_ingester.py`

**Modified files:**
- `src/ground_truth/officials.json` (city_leadership section)
- `web/src/app/api/health/route.ts` (migration group)
- `src/staleness_monitor.py` (schema health)

**Cost:** $0 (no Claude API calls — pure Socrata + keyword heuristics)
