"""
Richmond Transparency Project — Data Quality Regression Suite

SQL-based checks for known anti-patterns discovered during the
March 2026 data quality audit. Runs post-pipeline or on schedule
to catch silent data quality regressions.

Usage:
  python data_quality_checks.py                    # Text summary
  python data_quality_checks.py --format json      # JSON output
  python data_quality_checks.py --check            # Exit code 1 if issues found
  python data_quality_checks.py --create-decisions # Create decision queue entries

Checks:
  1. Sentinel strings in text fields (extraction artifacts)
  2. Missing item_number with title matching agenda numbering patterns
  3. Trailing commas or formatting issues in financial_amount
  4. Suspiciously low financial_amount values (< $100)
  5. Confidence-to-tier desynchronization in conflict flags
  6. Missing FIPS codes on any table
  7. Orphaned records (votes without meetings, motions without items)
  8. Empty required text fields (title, name)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from db import get_connection  # noqa: E402
from conflict_scanner import TIER_THRESHOLDS_BY_NUMBER  # noqa: E402

DEFAULT_FIPS = "0660620"

# Imported from conflict_scanner.py (single source of truth).
# Previously had stale v2 values (0.6/0.4/0.0) — now guaranteed in sync.
TIER_THRESHOLDS = TIER_THRESHOLDS_BY_NUMBER

# Sentinel strings that indicate extraction failures.
# These appear when PDF parsing or LLM extraction breaks silently.
SENTINEL_PATTERNS = [
    r"\(cid:\d+\)",          # PyMuPDF Type3 font fallback
    r"\\x[0-9a-fA-F]{2}",   # Escaped hex bytes
    r"\x00",                 # Null bytes
    r"â€™|â€œ|â€\x9d",     # Mojibake (UTF-8 decoded as Latin-1)
]


@dataclass
class QualityIssue:
    """A single data quality finding."""
    check_name: str
    severity: str  # "error", "warning", "info"
    description: str
    table: str
    count: int
    sample_ids: list[str] = field(default_factory=list)
    details: str = ""


# ── Individual Checks ─────────────────────────────────────────


def check_sentinel_strings(conn, city_fips: str = DEFAULT_FIPS) -> list[QualityIssue]:
    """Check for extraction artifact strings in text fields.

    Sentinel strings indicate silent PDF parsing or LLM extraction
    failures. Found in the March 2026 audit.
    """
    issues = []

    # Check agenda_items.title and agenda_items.description
    for col in ("title", "description"):
        for pattern in SENTINEL_PATTERNS:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT ai.id::text
                    FROM agenda_items ai
                    JOIN meetings m ON m.id = ai.meeting_id
                    WHERE m.city_fips = %s
                      AND ai.{col} ~ %s
                    LIMIT 10
                    """,
                    (city_fips, pattern),
                )
                rows = cur.fetchall()

            if rows:
                issues.append(QualityIssue(
                    check_name="sentinel_strings",
                    severity="error",
                    description=(
                        f"Found sentinel pattern {pattern!r} in "
                        f"agenda_items.{col}"
                    ),
                    table="agenda_items",
                    count=len(rows),
                    sample_ids=[r[0] for r in rows],
                ))

    # Check documents.extracted_text
    for pattern in SENTINEL_PATTERNS:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id::text
                FROM documents
                WHERE city_fips = %s
                  AND extracted_text ~ %s
                LIMIT 10
                """,
                (city_fips, pattern),
            )
            rows = cur.fetchall()

        if rows:
            issues.append(QualityIssue(
                check_name="sentinel_strings",
                severity="error",
                description=(
                    f"Found sentinel pattern {pattern!r} in "
                    f"documents.extracted_text"
                ),
                table="documents",
                count=len(rows),
                sample_ids=[r[0] for r in rows],
            ))

    return issues


def check_missing_item_numbers(conn, city_fips: str = DEFAULT_FIPS) -> list[QualityIssue]:
    """Check for agenda items with empty item_number but title matching
    agenda numbering patterns like 'A.1', 'H.3', 'I-1'.

    These indicate extraction failed to parse the item number from
    the title text.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ai.id::text, ai.title
            FROM agenda_items ai
            JOIN meetings m ON m.id = ai.meeting_id
            WHERE m.city_fips = %s
              AND (ai.item_number IS NULL OR ai.item_number = '')
              AND ai.title ~ '^[A-Z][-.]\\d+'
            LIMIT 20
            """,
            (city_fips,),
        )
        rows = cur.fetchall()

    if not rows:
        return []

    return [QualityIssue(
        check_name="missing_item_number",
        severity="warning",
        description=(
            "Agenda items with empty item_number but title matching "
            "numbering pattern (e.g., 'A.1', 'H.3')"
        ),
        table="agenda_items",
        count=len(rows),
        sample_ids=[r[0] for r in rows],
        details="; ".join(f"{r[0]}: {r[1][:60]}" for r in rows[:5]),
    )]


def check_financial_amount_formatting(conn, city_fips: str = DEFAULT_FIPS) -> list[QualityIssue]:
    """Check for formatting issues in financial_amount fields.

    Looks for trailing commas, dollar signs stored in numeric fields,
    or other parsing artifacts in contribution amounts.
    """
    issues = []

    # Check contributions for suspicious formatting in text representation
    # (amounts stored as numeric but may have been parsed incorrectly)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id::text, c.amount
            FROM contributions c
            JOIN donors d ON d.id = c.donor_id
            WHERE d.city_fips = %s
              AND c.amount IS NOT NULL
              AND c.amount < 0
            LIMIT 10
            """,
            (city_fips,),
        )
        rows = cur.fetchall()

    if rows:
        issues.append(QualityIssue(
            check_name="negative_contribution_amount",
            severity="warning",
            description="Contributions with negative amounts (possible parsing error)",
            table="contributions",
            count=len(rows),
            sample_ids=[r[0] for r in rows],
            details="; ".join(f"id={r[0]}: ${r[1]}" for r in rows[:5]),
        ))

    return issues


def check_suspicious_amounts(conn, city_fips: str = DEFAULT_FIPS) -> list[QualityIssue]:
    """Check for suspiciously low financial_amount values (< $100).

    Government contracts and contributions under $100 are unusual and
    may indicate decimal point parsing errors (e.g., $50000 -> $50.00).
    """
    # Check city expenditures for suspiciously low amounts
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'city_expenditures'
            )
            """,
        )
        has_expenditures = cur.fetchone()[0]

    if has_expenditures:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id::text, amount
                FROM city_expenditures
                WHERE city_fips = %s
                  AND amount IS NOT NULL
                  AND amount > 0 AND amount < 100
                LIMIT 10
                """,
                (city_fips,),
            )
            rows = cur.fetchall()

        if rows:
            return [QualityIssue(
                check_name="suspicious_low_amount",
                severity="info",
                description=(
                    "City expenditures under $100 (possible decimal "
                    "point parsing error)"
                ),
                table="city_expenditures",
                count=len(rows),
                sample_ids=[r[0] for r in rows],
                details="; ".join(f"id={r[0]}: ${r[1]}" for r in rows[:5]),
            )]

    return []


def check_confidence_tier_sync(conn, city_fips: str = DEFAULT_FIPS) -> list[QualityIssue]:
    """Check that conflict_flags.publication_tier matches the confidence
    score according to the canonical tier thresholds.

    This is the critical desynchronization found in the Q1 2026 audit:
    a flag with confidence 0.65 could be stored as tier 1 (by the scanner)
    but rendered as tier 2 (by the frontend using different thresholds).
    """
    issues = []

    # Find flags where stored tier doesn't match what the confidence
    # score should produce according to canonical thresholds
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                cf.id::text,
                cf.confidence,
                cf.publication_tier,
                CASE
                    WHEN cf.confidence >= %s THEN 1
                    WHEN cf.confidence >= %s THEN 2
                    ELSE 3
                END AS expected_tier
            FROM conflict_flags cf
            JOIN meetings m ON m.id = cf.meeting_id
            WHERE m.city_fips = %s
              AND cf.is_current = TRUE
              AND cf.publication_tier IS NOT NULL
              AND cf.publication_tier != (
                  CASE
                      WHEN cf.confidence >= %s THEN 1
                      WHEN cf.confidence >= %s THEN 2
                      ELSE 3
                  END
              )
            LIMIT 20
            """,
            (
                TIER_THRESHOLDS[1], TIER_THRESHOLDS[2], city_fips,
                TIER_THRESHOLDS[1], TIER_THRESHOLDS[2],
            ),
        )
        rows = cur.fetchall()

    if rows:
        issues.append(QualityIssue(
            check_name="confidence_tier_desync",
            severity="error",
            description=(
                f"Conflict flags where stored publication_tier doesn't match "
                f"confidence score (thresholds: tier1>={TIER_THRESHOLDS[1]}, "
                f"tier2>={TIER_THRESHOLDS[2]})"
            ),
            table="conflict_flags",
            count=len(rows),
            sample_ids=[r[0] for r in rows],
            details="; ".join(
                f"id={r[0]}: confidence={r[1]:.2f}, "
                f"stored_tier={r[2]}, expected_tier={r[3]}"
                for r in rows[:5]
            ),
        ))

    return issues


def check_missing_fips(conn, city_fips: str = DEFAULT_FIPS) -> list[QualityIssue]:
    """Check for records with NULL or empty city_fips.

    FIPS codes are non-negotiable per project conventions. Every record
    must have one.
    """
    issues = []

    tables_with_fips = [
        "meetings", "officials", "donors", "documents",
    ]

    for table in tables_with_fips:
        # First check if table exists
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = %s AND column_name = 'city_fips'
                )
                """,
                (table,),
            )
            has_column = cur.fetchone()[0]

        if not has_column:
            continue

        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*)
                FROM {table}
                WHERE city_fips IS NULL OR city_fips = ''
                """,
            )
            count = cur.fetchone()[0]

        if count > 0:
            issues.append(QualityIssue(
                check_name="missing_fips",
                severity="error",
                description=f"Records with NULL or empty city_fips in {table}",
                table=table,
                count=count,
            ))

    return issues


def check_orphaned_records(conn, city_fips: str = DEFAULT_FIPS) -> list[QualityIssue]:
    """Check for orphaned records: votes without meetings, motions
    without agenda items, agenda items without meetings.

    These indicate referential integrity issues from partial pipeline runs.
    """
    issues = []

    checks = [
        (
            "agenda_items without meetings",
            """
            SELECT ai.id::text
            FROM agenda_items ai
            LEFT JOIN meetings m ON m.id = ai.meeting_id
            WHERE m.id IS NULL
            LIMIT 10
            """,
            "agenda_items",
        ),
        (
            "motions without agenda items",
            """
            SELECT mo.id::text
            FROM motions mo
            LEFT JOIN agenda_items ai ON ai.id = mo.agenda_item_id
            WHERE ai.id IS NULL
            LIMIT 10
            """,
            "motions",
        ),
        (
            "votes without motions",
            """
            SELECT v.id::text
            FROM votes v
            LEFT JOIN motions mo ON mo.id = v.motion_id
            WHERE mo.id IS NULL
            LIMIT 10
            """,
            "votes",
        ),
        (
            "conflict_flags without meetings",
            """
            SELECT cf.id::text
            FROM conflict_flags cf
            LEFT JOIN meetings m ON m.id = cf.meeting_id
            WHERE m.id IS NULL
            LIMIT 10
            """,
            "conflict_flags",
        ),
    ]

    for description, query, table in checks:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()

        if rows:
            issues.append(QualityIssue(
                check_name="orphaned_records",
                severity="error",
                description=f"Orphaned: {description}",
                table=table,
                count=len(rows),
                sample_ids=[r[0] for r in rows],
            ))

    return issues


def check_empty_required_fields(conn, city_fips: str = DEFAULT_FIPS) -> list[QualityIssue]:
    """Check for empty required text fields that should never be blank.

    Officials without names, meetings without dates, agenda items
    without titles — these indicate extraction failures.
    """
    issues = []

    checks = [
        (
            "officials with empty name",
            """
            SELECT id::text FROM officials
            WHERE city_fips = %s AND (name IS NULL OR name = '')
            LIMIT 10
            """,
            "officials",
        ),
        (
            "agenda items with empty title",
            """
            SELECT ai.id::text
            FROM agenda_items ai
            JOIN meetings m ON m.id = ai.meeting_id
            WHERE m.city_fips = %s AND (ai.title IS NULL OR ai.title = '')
            LIMIT 10
            """,
            "agenda_items",
        ),
        (
            "donors with empty name",
            """
            SELECT id::text FROM donors
            WHERE city_fips = %s AND (name IS NULL OR name = '')
            LIMIT 10
            """,
            "donors",
        ),
    ]

    for description, query, table in checks:
        with conn.cursor() as cur:
            cur.execute(query, (city_fips,))
            rows = cur.fetchall()

        if rows:
            issues.append(QualityIssue(
                check_name="empty_required_field",
                severity="warning",
                description=f"Empty required field: {description}",
                table=table,
                count=len(rows),
                sample_ids=[r[0] for r in rows],
            ))

    return issues


def check_duplicate_contributions(conn, city_fips: str = DEFAULT_FIPS) -> list[QualityIssue]:
    """Check for duplicate contributions that slipped past deduplication.

    Duplicate contributions inflate financial connection signals.
    Exact duplicates on (donor_id, amount, contribution_date, committee_id)
    indicate amended filing dedup failure.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                d.name,
                c.amount,
                c.contribution_date,
                COUNT(*) AS dup_count
            FROM contributions c
            JOIN donors d ON d.id = c.donor_id
            WHERE d.city_fips = %s
            GROUP BY d.name, c.amount, c.contribution_date, c.committee_id
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC
            LIMIT 10
            """,
            (city_fips,),
        )
        rows = cur.fetchall()

    if not rows:
        return []

    total_dups = sum(r[3] - 1 for r in rows)  # extra copies beyond the first
    return [QualityIssue(
        check_name="duplicate_contributions",
        severity="warning",
        description=(
            f"Potential duplicate contributions "
            f"(same donor, amount, date, committee)"
        ),
        table="contributions",
        count=total_dups,
        details="; ".join(
            f"{r[0]}: ${r[1]} on {r[2]} ({r[3]}x)"
            for r in rows[:5]
        ),
    )]


# ── Suite Runner ──────────────────────────────────────────────


ALL_CHECKS = [
    check_sentinel_strings,
    check_missing_item_numbers,
    check_financial_amount_formatting,
    check_suspicious_amounts,
    check_confidence_tier_sync,
    check_missing_fips,
    check_orphaned_records,
    check_empty_required_fields,
    check_duplicate_contributions,
]


def run_all_checks(
    conn,
    city_fips: str = DEFAULT_FIPS,
    checks: list | None = None,
) -> dict:
    """Run all data quality checks and return structured results.

    Args:
        conn: Database connection
        city_fips: FIPS code to check
        checks: Optional subset of check functions to run

    Returns:
        Dict with overall status, issue counts, and per-check results.
    """
    check_fns = checks or ALL_CHECKS
    all_issues: list[QualityIssue] = []
    check_results = []

    for check_fn in check_fns:
        try:
            issues = check_fn(conn, city_fips=city_fips)
            all_issues.extend(issues)
            check_results.append({
                "check": check_fn.__name__,
                "status": "fail" if issues else "pass",
                "issue_count": len(issues),
                "issues": [asdict(i) for i in issues],
            })
        except Exception as e:
            check_results.append({
                "check": check_fn.__name__,
                "status": "error",
                "error": str(e),
                "issue_count": 0,
                "issues": [],
            })

    # Derive overall status
    error_count = sum(1 for i in all_issues if i.severity == "error")
    warning_count = sum(1 for i in all_issues if i.severity == "warning")
    check_errors = sum(1 for r in check_results if r["status"] == "error")

    if check_errors > 0:
        overall = "error"
    elif error_count > 0:
        overall = "fail"
    elif warning_count > 0:
        overall = "warning"
    else:
        overall = "pass"

    return {
        "overall_status": overall,
        "total_issues": len(all_issues),
        "error_count": error_count,
        "warning_count": warning_count,
        "info_count": sum(1 for i in all_issues if i.severity == "info"),
        "checks_run": len(check_results),
        "checks_passed": sum(1 for r in check_results if r["status"] == "pass"),
        "checks_failed": sum(1 for r in check_results if r["status"] == "fail"),
        "checks_errored": check_errors,
        "check_results": check_results,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "city_fips": city_fips,
    }


# ── Formatters ────────────────────────────────────────────────


def format_text_report(results: dict) -> str:
    """Format quality check results as a human-readable text report."""
    lines = [
        "Data Quality Regression Report",
        "=" * 50,
        f"Overall: {results['overall_status'].upper()}",
        f"Checks: {results['checks_passed']} passed, "
        f"{results['checks_failed']} failed, "
        f"{results['checks_errored']} errored "
        f"(of {results['checks_run']})",
        f"Issues: {results['error_count']} errors, "
        f"{results['warning_count']} warnings, "
        f"{results['info_count']} info",
        "",
    ]

    for result in results["check_results"]:
        status_icon = {
            "pass": "  OK",
            "fail": "FAIL",
            "error": " ERR",
        }.get(result["status"], "  ??")

        lines.append(f"  [{status_icon}] {result['check']}")

        if result["status"] == "error":
            lines.append(f"         Error: {result.get('error', 'unknown')}")

        for issue in result.get("issues", []):
            severity_tag = issue["severity"].upper()
            lines.append(
                f"         [{severity_tag}] {issue['description']} "
                f"({issue['count']} records in {issue['table']})"
            )
            if issue.get("details"):
                lines.append(f"         Details: {issue['details'][:200]}")
            if issue.get("sample_ids"):
                ids_str = ", ".join(issue["sample_ids"][:3])
                lines.append(f"         Sample IDs: {ids_str}")

    lines.append("")
    lines.append(f"Checked at: {results['checked_at']}")
    return "\n".join(lines)


# ── Decision Queue Integration ────────────────────────────────


def create_quality_decisions(
    conn,
    city_fips: str = DEFAULT_FIPS,
    results: dict | None = None,
) -> list[str]:
    """Create decision queue entries for data quality issues.

    Only creates entries for error and warning severity issues.
    Uses dedup_key to prevent duplicate entries.

    Returns list of created decision IDs.
    """
    from decision_queue import create_decision

    if results is None:
        results = run_all_checks(conn, city_fips)

    created = []
    today = datetime.now().strftime("%Y-%m-%d")

    for check_result in results["check_results"]:
        for issue in check_result.get("issues", []):
            if issue["severity"] not in ("error", "warning"):
                continue

            severity_map = {"error": "high", "warning": "medium"}

            result = create_decision(
                conn,
                city_fips=city_fips,
                decision_type="data_quality",
                severity=severity_map.get(issue["severity"], "medium"),
                title=f"Data quality: {issue['check_name']}",
                description=issue["description"],
                source="data_quality_checks",
                evidence={
                    "check_name": issue["check_name"],
                    "table": issue["table"],
                    "count": issue["count"],
                    "sample_ids": issue.get("sample_ids", [])[:5],
                    "details": issue.get("details", ""),
                },
                dedup_key=f"dq:{issue['check_name']}:{issue['table']}:{today}",
            )
            if result is not None:
                created.append(str(result))

    return created


# ── CLI ───────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Data Quality Regression Suite — check for known anti-patterns"
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit with code 1 if errors or warnings exist",
    )
    parser.add_argument(
        "--city-fips",
        default=DEFAULT_FIPS,
        help=f"City FIPS code (default: {DEFAULT_FIPS})",
    )
    parser.add_argument(
        "--create-decisions",
        action="store_true",
        help="Create decision queue entries for issues found",
    )

    args = parser.parse_args()

    conn = get_connection()
    try:
        results = run_all_checks(conn, city_fips=args.city_fips)
    finally:
        conn.close()

    if args.format == "json":
        print(json.dumps(results, indent=2, default=str))
    else:
        print(format_text_report(results))

    if args.create_decisions:
        conn2 = get_connection()
        try:
            created = create_quality_decisions(
                conn2, city_fips=args.city_fips, results=results,
            )
            if created:
                print(f"\nCreated {len(created)} quality decision(s).")
            else:
                print("\nNo new quality decisions created.")
        finally:
            conn2.close()

    if args.check:
        has_issues = results["overall_status"] in ("fail", "error")
        sys.exit(1 if has_issues else 0)


if __name__ == "__main__":
    main()
