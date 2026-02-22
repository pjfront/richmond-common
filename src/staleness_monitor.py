"""
Richmond Transparency Project — Data Freshness Monitor

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

from db import get_connection, RICHMOND_FIPS  # noqa: E402

# ── Staleness Thresholds ─────────────────────────────────────

FRESHNESS_THRESHOLDS: dict[str, int] = {
    "netfile": 14,
    "calaccess": 45,
    "escribemeetings": 7,
    "archive_center": 45,
    "nextrequest": 7,
    "socrata_payroll": 45,
    "socrata_expenditures": 45,
}


def get_sync_freshness(
    conn,
    city_fips: str = RICHMOND_FIPS,
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
        default=RICHMOND_FIPS,
        help=f"City FIPS code (default: {RICHMOND_FIPS})",
    )

    args = parser.parse_args()

    conn = get_connection()
    try:
        freshness = get_sync_freshness(conn, city_fips=args.city_fips)
    finally:
        conn.close()

    if args.format == "json":
        output = freshness if not args.alert_only else [
            item for item in freshness if item["is_stale"]
        ]
        print(json.dumps(output, indent=2, default=str))
    else:
        print(format_text_report(freshness, alert_only=args.alert_only))

    if args.check:
        any_stale = any(item["is_stale"] for item in freshness)
        sys.exit(1 if any_stale else 0)


if __name__ == "__main__":
    main()
