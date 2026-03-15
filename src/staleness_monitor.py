"""
Richmond Common — Data Freshness Monitor

Queries data_sync_log for the most recent successful sync per source
and reports staleness against configurable thresholds.

Usage:
  python staleness_monitor.py                    # Text summary
  python staleness_monitor.py --format json      # JSON output
  python staleness_monitor.py --alert-only       # Only show stale sources
  python staleness_monitor.py --check            # Exit code 1 if any source is stale

Thresholds (from cloud-pipeline-spec.md):
  NetFile:        14 days
  CAL-ACCESS:     45 days
  eSCRIBE:         7 days
  Archive Center: 45 days
  NextRequest:     7 days
  Socrata:        45 days

This script is intended for:
  - n8n workflows that check freshness before triggering syncs
  - GitHub Actions for weekly freshness reports
  - Future: frontend /api/data-freshness endpoint
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from city_config import get_city_config  # noqa: E402
from db import get_connection  # noqa: E402

DEFAULT_FIPS = "0660620"  # Richmond — keep as CLI default for backward compat

# ── Expected Tables (grouped by migration) ───────────────────

EXPECTED_TABLES: dict[str, list[str]] = {
    "core_schema": [
        "cities", "officials", "meetings", "agenda_items",
        "motions", "votes", "contributions", "documents", "conflict_flags",
    ],
    "001_cloud_pipeline": ["scan_runs", "data_sync_log"],
    "002_user_feedback": ["user_feedback"],
    "003_nextrequest": ["nextrequest_requests", "nextrequest_documents"],
    "004_city_employees": ["city_employees"],
    "005_commissions": ["commissions", "commission_members"],
    "015_pipeline_journal": ["pipeline_journal"],
    "016_pending_decisions": ["pending_decisions"],
    "039_socrata_regulatory": [
        "city_permits", "city_licenses", "city_code_cases",
        "city_service_requests", "city_projects",
    ],
}

# ── Staleness Thresholds ─────────────────────────────────────

FRESHNESS_THRESHOLDS: dict[str, int] = {
    "netfile": 14,
    "calaccess": 45,
    "escribemeetings": 7,
    "archive_center": 45,
    "nextrequest": 7,
    "socrata_payroll": 45,
    "socrata_expenditures": 45,
    "socrata_permits": 30,
    "socrata_licenses": 45,
    "socrata_code_cases": 30,
    "socrata_service_requests": 30,
    "socrata_projects": 45,
    "form700": 90,
    "minutes_extraction": 14,
}


def check_schema_health(conn) -> dict:
    """Check which expected tables exist in the database.

    Returns a dict with:
      - status: 'healthy' | 'degraded' | 'unhealthy'
      - migrations: per-group results with applied/tables/missing
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            """
        )
        existing = {row[0] for row in cur.fetchall()}

    migrations: dict[str, dict] = {}
    total_missing = 0
    core_missing = False

    for group, tables in EXPECTED_TABLES.items():
        present = [t for t in tables if t in existing]
        missing = [t for t in tables if t not in existing]
        total_missing += len(missing)

        if not missing:
            migrations[group] = {"applied": True, "tables": present}
        else:
            migrations[group] = {"applied": False}
            if present:
                migrations[group]["tables"] = present
            migrations[group]["missing"] = missing
            if group == "core_schema":
                core_missing = True

    if total_missing == 0:
        status = "healthy"
    elif core_missing:
        status = "unhealthy"
    else:
        status = "degraded"

    return {"status": status, "migrations": migrations}


def format_schema_report(health: dict, alert_only: bool = False) -> str:
    """Format schema health as a human-readable text section."""
    lines = ["Schema Health", "=" * 40]

    if health["status"] == "healthy" and alert_only:
        return ""

    for group, info in health["migrations"].items():
        if alert_only and info["applied"]:
            continue
        status = "OK" if info["applied"] else "MISSING"
        label = group.ljust(22)
        if info["applied"]:
            lines.append(f"  [{status:7}] {label}  all tables present")
        else:
            missing = ", ".join(info["missing"])
            lines.append(f"  [{status:7}] {label}  missing: {missing}")

    lines.append("")
    lines.append(f"Overall: {health['status']}")
    return "\n".join(lines)


def get_sync_freshness(
    conn,
    city_fips: str = DEFAULT_FIPS,
) -> list[dict]:
    """Query data_sync_log for the latest successful sync per source.

    Returns a list of dicts with: source, last_sync, threshold_days,
    days_since_sync, is_stale.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT source, MAX(completed_at) AS last_sync
            FROM data_sync_log
            WHERE city_fips = %s AND status = 'completed'
            GROUP BY source
            ORDER BY source
            """,
            (city_fips,),
        )
        rows = cur.fetchall()

    # Build a map of source -> last_sync
    sync_map: dict[str, datetime] = {}
    for source, last_sync in rows:
        if last_sync:
            sync_map[source] = last_sync

    now = datetime.now(timezone.utc)
    results = []

    for source, threshold_days in FRESHNESS_THRESHOLDS.items():
        last_sync = sync_map.get(source)
        if last_sync:
            # Ensure timezone-aware comparison
            if last_sync.tzinfo is None:
                last_sync = last_sync.replace(tzinfo=timezone.utc)
            days_since = (now - last_sync).total_seconds() / 86400
            results.append({
                "source": source,
                "last_sync": last_sync.isoformat(),
                "threshold_days": threshold_days,
                "days_since_sync": round(days_since, 1),
                "is_stale": days_since > threshold_days,
            })
        else:
            results.append({
                "source": source,
                "last_sync": None,
                "threshold_days": threshold_days,
                "days_since_sync": None,
                "is_stale": True,  # Never synced = stale
            })

    return results


def format_text_report(freshness: list[dict], alert_only: bool = False) -> str:
    """Format freshness data as a human-readable text report."""
    lines = ["Data Source Freshness Report", "=" * 40]

    for item in freshness:
        if alert_only and not item["is_stale"]:
            continue

        status = "STALE" if item["is_stale"] else "OK"
        source = item["source"].ljust(22)

        if item["last_sync"]:
            days = item["days_since_sync"]
            threshold = item["threshold_days"]
            lines.append(
                f"  [{status:5}] {source}  "
                f"{days:.0f}d since sync (threshold: {threshold}d)"
            )
        else:
            lines.append(
                f"  [{status:5}] {source}  "
                f"Never synced (threshold: {item['threshold_days']}d)"
            )

    stale_count = sum(1 for item in freshness if item["is_stale"])
    total = len(freshness)
    lines.append("")
    lines.append(f"Summary: {stale_count}/{total} sources stale")

    return "\n".join(lines)


def create_staleness_decisions(
    conn,
    city_fips: str = DEFAULT_FIPS,
) -> list[str]:
    """Create decision queue entries for stale data sources.

    Calls get_sync_freshness(), creates staleness_alert decisions
    for any source that is stale. Uses dedup_key to prevent duplicates.

    Returns list of created decision IDs (UUIDs as strings).
    """
    from decision_queue import create_decision

    freshness = get_sync_freshness(conn, city_fips=city_fips)
    created = []

    for item in freshness:
        if not item["is_stale"]:
            continue

        source = item["source"]
        threshold = item["threshold_days"]
        days_since = item["days_since_sync"]

        # Severity: high if >2x threshold or never synced, medium otherwise
        if days_since is None or days_since > threshold * 2:
            severity = "high"
        else:
            severity = "medium"

        if days_since is not None:
            title = f"{source} data is {days_since:.0f} days stale"
            description = (
                f"Last sync {days_since:.0f} days ago, "
                f"threshold is {threshold} days."
            )
        else:
            title = f"{source} has never been synced"
            description = (
                f"No successful sync recorded. "
                f"Freshness threshold is {threshold} days."
            )

        result = create_decision(
            conn,
            city_fips=city_fips,
            decision_type="staleness_alert",
            severity=severity,
            title=title,
            description=description,
            source="staleness_monitor",
            evidence={
                "days_since_sync": days_since,
                "threshold_days": threshold,
                "source_name": source,
            },
            link="https://rtp-gray.vercel.app/data-quality",
            dedup_key=f"staleness:{source}",
        )
        if result is not None:
            created.append(str(result))

    return created


def main():
    parser = argparse.ArgumentParser(
        description="Check data source freshness against staleness thresholds"
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--alert-only",
        action="store_true",
        help="Only show stale sources",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit with code 1 if any source is stale",
    )
    parser.add_argument(
        "--city-fips",
        default=DEFAULT_FIPS,
        help=f"City FIPS code (default: {DEFAULT_FIPS})",
    )
    parser.add_argument(
        "--create-decisions",
        action="store_true",
        help="Create decision queue entries for stale sources",
    )

    args = parser.parse_args()

    conn = get_connection()
    try:
        schema_health = check_schema_health(conn)
        freshness = get_sync_freshness(conn, city_fips=args.city_fips)
    finally:
        conn.close()

    if args.format == "json":
        freshness_output = freshness if not args.alert_only else [
            item for item in freshness if item["is_stale"]
        ]
        output = {
            "schema": schema_health,
            "freshness": freshness_output,
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        schema_text = format_schema_report(
            schema_health, alert_only=args.alert_only
        )
        if schema_text:
            print(schema_text)
            print()
        print(format_text_report(freshness, alert_only=args.alert_only))

    if args.create_decisions:
        conn2 = get_connection()
        try:
            created = create_staleness_decisions(conn2, city_fips=args.city_fips)
            if created:
                print(f"\nCreated {len(created)} staleness decision(s).")
            else:
                print("\nNo new staleness decisions created (all deduplicated or fresh).")
        finally:
            conn2.close()

    if args.check:
        any_stale = any(item["is_stale"] for item in freshness)
        schema_bad = schema_health["status"] != "healthy"
        sys.exit(1 if (any_stale or schema_bad) else 0)


if __name__ == "__main__":
    main()
