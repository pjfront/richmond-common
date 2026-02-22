"""
Socrata payroll ingester for city employee hierarchy.

Fetches payroll data from Transparent Richmond (Socrata), normalizes names,
aggregates per-transaction rows by employee, classifies hierarchy by title
keywords, and stores in city_employees table.

Socrata payroll data is at the *transaction* level (one row per pay check per
account), so we must aggregate by (employeeid, fiscalyear) to get one record
per employee with annual totals.

Usage:
    python payroll_ingester.py --fiscal-year 2025 --stats
    python payroll_ingester.py --fiscal-year 2025 --output employees.json
    python payroll_ingester.py --fiscal-year 2025 --load
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

# ── Socrata field names (discovered via `python socrata_client.py payroll --list-columns`) ──
# The payroll dataset (crbs-mam9) uses these column names:
#   firstname, lastname     — employee name (ALL CAPS)
#   position                — job title (ALL CAPS)
#   department              — department name (ALL CAPS)
#   employeeid              — stable employee identifier
#   basepay                 — base pay per transaction
#   otherpay                — other pay per transaction
#   overtimepay             — overtime pay per transaction
#   benefitsamount          — benefits per transaction
#   totalpay                — total pay per transaction (sum of above)
#   fiscalyear              — fiscal year (number)
#   positiontype            — employment type (FULL TIME PERMANENT, etc.)


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


def _title_case_name(name: str) -> str:
    """Convert ALL CAPS name to title case, preserving suffixes."""
    parts = name.strip().split()
    result = []
    for part in parts:
        # Handle suffixes like "IV", "III", "II", "JR", "SR"
        if part.upper() in ("II", "III", "IV", "V", "JR", "SR", "JR.", "SR."):
            result.append(part.upper())
        else:
            result.append(part.capitalize())
    return " ".join(result)


def normalize_employee(row: dict) -> dict:
    """Extract and normalize fields from a Socrata payroll row."""
    first = (row.get("firstname") or "").strip()
    last = (row.get("lastname") or "").strip()
    raw_name = f"{first} {last}".strip()
    name = _title_case_name(raw_name) if raw_name else ""

    return {
        "employee_id": (row.get("employeeid") or "").strip(),
        "name": name,
        "normalized_name": _normalize_name(name) if name else "",
        "job_title": (row.get("position") or "").strip(),
        "department": (row.get("department") or "").strip(),
        "basepay": _safe_float(row.get("basepay")),
        "otherpay": _safe_float(row.get("otherpay")),
        "overtimepay": _safe_float(row.get("overtimepay")),
        "benefitsamount": _safe_float(row.get("benefitsamount")),
        "totalpay": _safe_float(row.get("totalpay")),
        "fiscal_year": str(row.get("fiscalyear") or "").strip(),
        "position_type": (row.get("positiontype") or "").strip(),
    }


def aggregate_by_employee(rows: list[dict]) -> list[dict]:
    """Aggregate per-transaction payroll rows into one record per employee.

    Groups by (employeeid, fiscalyear) and sums pay fields.
    Keeps the first-seen position, department, and name.
    """
    if not rows:
        return []

    grouped: dict[str, dict] = {}
    for row in rows:
        eid = (row.get("employeeid") or "").strip()
        fy = str(row.get("fiscalyear") or "").strip()
        key = f"{eid}:{fy}"

        if key not in grouped:
            grouped[key] = {
                "employeeid": eid,
                "firstname": (row.get("firstname") or "").strip(),
                "lastname": (row.get("lastname") or "").strip(),
                "position": (row.get("position") or "").strip(),
                "department": (row.get("department") or "").strip(),
                "basepay": 0.0,
                "otherpay": 0.0,
                "overtimepay": 0.0,
                "benefitsamount": 0.0,
                "totalpay": 0.0,
                "fiscalyear": fy,
                "positiontype": (row.get("positiontype") or "").strip(),
            }

        rec = grouped[key]
        rec["basepay"] += _safe_float(row.get("basepay")) or 0.0
        rec["otherpay"] += _safe_float(row.get("otherpay")) or 0.0
        rec["overtimepay"] += _safe_float(row.get("overtimepay")) or 0.0
        rec["benefitsamount"] += _safe_float(row.get("benefitsamount")) or 0.0
        rec["totalpay"] += _safe_float(row.get("totalpay")) or 0.0

    return list(grouped.values())


def build_employee_record(row: dict, *, city_fips: str = CITY_FIPS) -> dict:
    """Build a complete employee record with hierarchy classification."""
    emp = normalize_employee(row)
    level, is_head = classify_title(emp["job_title"])
    return {
        "city_fips": city_fips,
        "name": emp["name"],
        "normalized_name": emp["normalized_name"],
        "job_title": emp["job_title"],
        "department": emp["department"],
        "hierarchy_level": level,
        "is_department_head": is_head,
        "annual_salary": emp["basepay"],
        "total_compensation": emp["totalpay"],
        "fiscal_year": emp["fiscal_year"],
        "source": "socrata_payroll",
        "socrata_record_id": emp["employee_id"],
        "is_current": True,
    }


def parse_payroll_records(
    rows: list[dict], *, city_fips: str = CITY_FIPS
) -> list[dict]:
    """Parse a batch of Socrata payroll rows into employee records.

    Aggregates per-transaction rows by employee, then classifies hierarchy.
    Skips rows with empty names.
    """
    aggregated = aggregate_by_employee(rows)
    records = []
    for row in aggregated:
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
    return query_dataset(
        "payroll",
        where=f"fiscalyear = '{fiscal_year}'",
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
    Designed for <2 min review -- just confirm the right people are flagged.
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
    parser.add_argument("--fiscal-year", default="2025", help="Fiscal year to fetch")
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
    logger.info("Fetched %d raw transaction rows from Socrata", len(raw_rows))

    records = parse_payroll_records(raw_rows, city_fips=fips)
    logger.info("Parsed %d unique employee records", len(records))

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
                        total_compensation, fiscal_year, is_current, source,
                        socrata_record_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT ON CONSTRAINT uq_city_employee
                       DO UPDATE SET
                           job_title = EXCLUDED.job_title,
                           is_department_head = EXCLUDED.is_department_head,
                           hierarchy_level = EXCLUDED.hierarchy_level,
                           annual_salary = EXCLUDED.annual_salary,
                           total_compensation = EXCLUDED.total_compensation,
                           is_current = EXCLUDED.is_current,
                           source = EXCLUDED.source,
                           socrata_record_id = EXCLUDED.socrata_record_id,
                           updated_at = NOW()""",
                    (
                        rec["city_fips"], rec["name"], rec["normalized_name"],
                        rec["job_title"], rec["department"],
                        rec["is_department_head"], rec["hierarchy_level"],
                        rec["annual_salary"], rec["total_compensation"],
                        rec["fiscal_year"], rec["is_current"], rec["source"],
                        rec.get("socrata_record_id"),
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
