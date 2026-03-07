"""
Richmond Transparency Project -- Data Completeness Monitor

Checks meeting data for completeness and anomalies: are agenda items,
votes, and attendance records present? Are document URLs available?
Do recent meetings deviate from historical baselines?

Usage:
  python completeness_monitor.py                    # Text summary
  python completeness_monitor.py --format json      # JSON output
  python completeness_monitor.py --alert-only       # Only show anomalies
  python completeness_monitor.py --check            # Exit code 1 if anomalies exist

Complements staleness_monitor.py (which checks data source freshness).
This module checks the quality/completeness of the data itself.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from db import get_connection  # noqa: E402

DEFAULT_FIPS = "0660620"

# Completeness score weights (must sum to 100)
WEIGHT_ITEMS = 30
WEIGHT_VOTES = 30
WEIGHT_ATTENDANCE = 20
WEIGHT_URLS = 20

# Anomaly threshold: flag if value deviates more than this many
# standard deviations from the historical mean
ANOMALY_STDDEV_THRESHOLD = 2.0


# -- Core Check Functions ---------------------------------------------------


def get_meeting_completeness(
    conn,
    city_fips: str = DEFAULT_FIPS,
    limit: int = 20,
) -> list[dict]:
    """Check completeness of recent meetings.

    Returns per-meeting completeness data: counts of items, votes,
    attendance records, URL availability, and a weighted score (0-100).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                m.id,
                m.meeting_date,
                m.meeting_type,
                m.minutes_url,
                m.agenda_url,
                m.video_url,
                COALESCE(ai.cnt, 0) AS agenda_item_count,
                COALESCE(v.cnt, 0) AS vote_count,
                COALESCE(att.cnt, 0) AS attendance_count
            FROM meetings m
            LEFT JOIN (
                SELECT meeting_id, COUNT(*) AS cnt
                FROM agenda_items
                GROUP BY meeting_id
            ) ai ON ai.meeting_id = m.id
            LEFT JOIN (
                SELECT ai2.meeting_id, COUNT(v2.id) AS cnt
                FROM votes v2
                JOIN motions mo ON mo.id = v2.motion_id
                JOIN agenda_items ai2 ON ai2.id = mo.agenda_item_id
                GROUP BY ai2.meeting_id
            ) v ON v.meeting_id = m.id
            LEFT JOIN (
                SELECT meeting_id, COUNT(*) AS cnt
                FROM meeting_attendance
                GROUP BY meeting_id
            ) att ON att.meeting_id = m.id
            WHERE m.city_fips = %s
            ORDER BY m.meeting_date DESC
            LIMIT %s
            """,
            (city_fips, limit),
        )
        rows = cur.fetchall()

    results = []
    for row in rows:
        (
            meeting_id, meeting_date, meeting_type,
            minutes_url, agenda_url, video_url,
            item_count, vote_count, att_count,
        ) = row

        has_items = item_count > 0
        has_votes = vote_count > 0
        has_attendance = att_count > 0
        has_minutes = bool(minutes_url)
        has_agenda = bool(agenda_url)
        has_video = bool(video_url)

        # Weighted completeness score
        score = 0
        if has_items:
            score += WEIGHT_ITEMS
        if has_votes:
            score += WEIGHT_VOTES
        if has_attendance:
            score += WEIGHT_ATTENDANCE
        url_score = sum([has_minutes, has_agenda, has_video]) / 3
        score += int(WEIGHT_URLS * url_score)

        results.append({
            "meeting_id": str(meeting_id),
            "meeting_date": str(meeting_date),
            "meeting_type": meeting_type,
            "agenda_item_count": item_count,
            "vote_count": vote_count,
            "attendance_count": att_count,
            "has_minutes": has_minutes,
            "has_agenda": has_agenda,
            "has_video": has_video,
            "completeness_score": score,
        })

    return results


def get_document_coverage(
    conn,
    city_fips: str = DEFAULT_FIPS,
) -> dict:
    """Track document URL coverage across all meetings.

    Returns total meeting count and coverage percentages for minutes,
    agenda, and video URLs.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(minutes_url) AS has_minutes,
                COUNT(agenda_url) AS has_agenda,
                COUNT(video_url) AS has_video
            FROM meetings
            WHERE city_fips = %s
            """,
            (city_fips,),
        )
        row = cur.fetchone()

    total = row[0] if row else 0
    if total == 0:
        return {
            "total_meetings": 0,
            "minutes": {"count": 0, "percentage": 0.0},
            "agenda": {"count": 0, "percentage": 0.0},
            "video": {"count": 0, "percentage": 0.0},
        }

    return {
        "total_meetings": total,
        "minutes": {
            "count": row[1],
            "percentage": round(row[1] / total * 100, 1),
        },
        "agenda": {
            "count": row[2],
            "percentage": round(row[2] / total * 100, 1),
        },
        "video": {
            "count": row[3],
            "percentage": round(row[3] / total * 100, 1),
        },
    }


def get_trend_anomalies(
    conn,
    city_fips: str = DEFAULT_FIPS,
    recent_count: int = 5,
) -> list[dict]:
    """Compare recent meetings against historical baseline.

    Computes mean and standard deviation of agenda item counts and
    vote counts for regular meetings, then flags recent meetings
    that deviate beyond the threshold.
    """
    # Get historical baseline for regular meetings
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                COALESCE(AVG(ai.cnt), 0) AS avg_items,
                COALESCE(STDDEV(ai.cnt), 0) AS stddev_items,
                COALESCE(AVG(v.cnt), 0) AS avg_votes,
                COALESCE(STDDEV(v.cnt), 0) AS stddev_votes,
                COUNT(*) AS meeting_count
            FROM meetings m
            LEFT JOIN (
                SELECT meeting_id, COUNT(*) AS cnt
                FROM agenda_items
                GROUP BY meeting_id
            ) ai ON ai.meeting_id = m.id
            LEFT JOIN (
                SELECT ai2.meeting_id, COUNT(v2.id) AS cnt
                FROM votes v2
                JOIN motions mo ON mo.id = v2.motion_id
                JOIN agenda_items ai2 ON ai2.id = mo.agenda_item_id
                GROUP BY ai2.meeting_id
            ) v ON v.meeting_id = m.id
            WHERE m.city_fips = %s AND m.meeting_type = 'regular'
            """,
            (city_fips,),
        )
        baseline_row = cur.fetchone()

    if not baseline_row or baseline_row[4] < 3:
        # Not enough data for meaningful baseline
        return []

    avg_items = float(baseline_row[0])
    stddev_items = float(baseline_row[1])
    avg_votes = float(baseline_row[2])
    stddev_votes = float(baseline_row[3])

    # Get recent meetings (all types, not just regular)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                m.id,
                m.meeting_date,
                m.meeting_type,
                COALESCE(ai.cnt, 0) AS item_count,
                COALESCE(v.cnt, 0) AS vote_count,
                COALESCE(att.cnt, 0) AS attendance_count
            FROM meetings m
            LEFT JOIN (
                SELECT meeting_id, COUNT(*) AS cnt
                FROM agenda_items
                GROUP BY meeting_id
            ) ai ON ai.meeting_id = m.id
            LEFT JOIN (
                SELECT ai2.meeting_id, COUNT(v2.id) AS cnt
                FROM votes v2
                JOIN motions mo ON mo.id = v2.motion_id
                JOIN agenda_items ai2 ON ai2.id = mo.agenda_item_id
                GROUP BY ai2.meeting_id
            ) v ON v.meeting_id = m.id
            LEFT JOIN (
                SELECT meeting_id, COUNT(*) AS cnt
                FROM meeting_attendance
                GROUP BY meeting_id
            ) att ON att.meeting_id = m.id
            WHERE m.city_fips = %s
            ORDER BY m.meeting_date DESC
            LIMIT %s
            """,
            (city_fips, recent_count),
        )
        recent_rows = cur.fetchall()

    anomalies = []
    threshold = ANOMALY_STDDEV_THRESHOLD

    for row in recent_rows:
        meeting_id, meeting_date, meeting_type, item_count, vote_count, att_count = row

        # Only apply item/vote baseline checks to regular meetings
        if meeting_type == "regular":
            # Item count anomaly
            if stddev_items > 0 and abs(item_count - avg_items) > threshold * stddev_items:
                direction = "low" if item_count < avg_items else "high"
                anomalies.append({
                    "meeting_id": str(meeting_id),
                    "meeting_date": str(meeting_date),
                    "anomaly_type": f"{direction}_item_count",
                    "description": (
                        f"{item_count} agenda items "
                        f"(avg: {avg_items:.0f}, range: "
                        f"{avg_items - threshold * stddev_items:.0f}-"
                        f"{avg_items + threshold * stddev_items:.0f})"
                    ),
                    "severity": "alert" if item_count == 0 else "warning",
                })

            # Vote count anomaly
            if stddev_votes > 0 and abs(vote_count - avg_votes) > threshold * stddev_votes:
                direction = "low" if vote_count < avg_votes else "high"
                anomalies.append({
                    "meeting_id": str(meeting_id),
                    "meeting_date": str(meeting_date),
                    "anomaly_type": f"{direction}_vote_count",
                    "description": (
                        f"{vote_count} votes "
                        f"(avg: {avg_votes:.0f}, range: "
                        f"{avg_votes - threshold * stddev_votes:.0f}-"
                        f"{avg_votes + threshold * stddev_votes:.0f})"
                    ),
                    "severity": "alert" if vote_count == 0 else "warning",
                })

        # Zero items is always an alert regardless of meeting type
        if item_count == 0:
            # Avoid duplicate if already flagged above
            already_flagged = any(
                a["meeting_id"] == str(meeting_id) and "item_count" in a["anomaly_type"]
                for a in anomalies
            )
            if not already_flagged:
                anomalies.append({
                    "meeting_id": str(meeting_id),
                    "meeting_date": str(meeting_date),
                    "anomaly_type": "no_items",
                    "description": "Meeting has no agenda items",
                    "severity": "alert",
                })

        # No attendance data
        if att_count == 0:
            anomalies.append({
                "meeting_id": str(meeting_id),
                "meeting_date": str(meeting_date),
                "anomaly_type": "no_attendance",
                "description": "No attendance records",
                "severity": "warning",
            })

    return anomalies


def get_completeness_summary(
    conn,
    city_fips: str = DEFAULT_FIPS,
) -> dict:
    """Aggregate completeness check combining all sub-checks.

    Returns overall status, meeting completeness stats, document
    coverage, and anomalies.
    """
    meetings = get_meeting_completeness(conn, city_fips, limit=20)
    coverage = get_document_coverage(conn, city_fips)
    anomalies = get_trend_anomalies(conn, city_fips)

    # Count meetings with all core data (items + votes + attendance)
    complete = sum(
        1 for m in meetings
        if m["agenda_item_count"] > 0
        and m["vote_count"] > 0
        and m["attendance_count"] > 0
    )

    # Derive overall status from anomalies
    alert_count = sum(1 for a in anomalies if a["severity"] == "alert")
    warning_count = sum(1 for a in anomalies if a["severity"] == "warning")

    if alert_count > 0:
        overall_status = "alert"
    elif warning_count > 0:
        overall_status = "warning"
    else:
        overall_status = "healthy"

    return {
        "overall_status": overall_status,
        "meeting_completeness": {
            "checked": len(meetings),
            "complete": complete,
            "recent_meetings": meetings,
        },
        "document_coverage": coverage,
        "anomalies": anomalies,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


# -- Formatters --------------------------------------------------------------


def format_text_report(summary: dict, alert_only: bool = False) -> str:
    """Format completeness summary as a human-readable text report."""
    lines = ["Data Completeness Report", "=" * 40]

    # Overall status
    status = summary["overall_status"].upper()
    lines.append(f"Overall: {status}")
    lines.append("")

    # Meeting completeness
    mc = summary["meeting_completeness"]
    if not alert_only:
        lines.append(
            f"Meeting Completeness: {mc['complete']}/{mc['checked']} "
            f"recent meetings have items + votes + attendance"
        )
        lines.append("")

    # Document coverage
    cov = summary["document_coverage"]
    if not alert_only and cov["total_meetings"] > 0:
        lines.append(f"Document Coverage ({cov['total_meetings']} meetings)")
        lines.append(f"  Minutes:  {cov['minutes']['percentage']:5.1f}%  ({cov['minutes']['count']})")
        lines.append(f"  Agenda:   {cov['agenda']['percentage']:5.1f}%  ({cov['agenda']['count']})")
        lines.append(f"  Video:    {cov['video']['percentage']:5.1f}%  ({cov['video']['count']})")
        lines.append("")

    # Anomalies
    anomalies = summary["anomalies"]
    if anomalies:
        lines.append(f"Anomalies ({len(anomalies)})")
        lines.append("-" * 40)
        for a in anomalies:
            severity = "!!" if a["severity"] == "alert" else "! "
            lines.append(
                f"  [{severity}] {a['meeting_date']}  "
                f"{a['anomaly_type']}: {a['description']}"
            )
    elif not alert_only:
        lines.append("No anomalies detected.")

    return "\n".join(lines)


# -- CLI ---------------------------------------------------------------------


def create_anomaly_decisions(
    conn,
    city_fips: str = DEFAULT_FIPS,
) -> list[str]:
    """Create decision queue entries for data completeness anomalies.

    Calls get_trend_anomalies(), creates anomaly decisions for each
    finding. Uses dedup_key to prevent duplicates.

    Returns list of created decision IDs (UUIDs as strings).
    """
    from decision_queue import create_decision

    anomalies = get_trend_anomalies(conn, city_fips=city_fips)
    created = []

    for anomaly in anomalies:
        meeting_id = anomaly["meeting_id"]
        anomaly_type = anomaly["anomaly_type"]

        # Map completeness severity to decision queue severity
        severity = "high" if anomaly["severity"] == "alert" else "medium"

        result = create_decision(
            conn,
            city_fips=city_fips,
            decision_type="anomaly",
            severity=severity,
            title=f"{anomaly_type} in meeting {anomaly['meeting_date']}",
            description=anomaly["description"],
            source="completeness_monitor",
            evidence={
                "anomaly_type": anomaly_type,
                "meeting_date": anomaly["meeting_date"],
            },
            entity_type="meeting",
            entity_id=meeting_id,
            link=f"https://rtp-gray.vercel.app/meetings/{meeting_id}",
            dedup_key=f"anomaly:{meeting_id}:{anomaly_type}",
        )
        if result is not None:
            created.append(str(result))

    return created


def main():
    parser = argparse.ArgumentParser(
        description="Check meeting data completeness and detect anomalies"
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
        help="Only show anomalies and alerts",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit with code 1 if anomalies exist",
    )
    parser.add_argument(
        "--city-fips",
        default=DEFAULT_FIPS,
        help=f"City FIPS code (default: {DEFAULT_FIPS})",
    )
    parser.add_argument(
        "--create-decisions",
        action="store_true",
        help="Create decision queue entries for anomalies",
    )

    args = parser.parse_args()

    conn = get_connection()
    try:
        summary = get_completeness_summary(conn, city_fips=args.city_fips)
    finally:
        conn.close()

    if args.format == "json":
        output = summary
        if args.alert_only:
            output = {
                "overall_status": summary["overall_status"],
                "anomalies": summary["anomalies"],
                "checked_at": summary["checked_at"],
            }
        print(json.dumps(output, indent=2, default=str))
    else:
        print(format_text_report(summary, alert_only=args.alert_only))

    if args.create_decisions:
        conn2 = get_connection()
        try:
            created = create_anomaly_decisions(conn2, city_fips=args.city_fips)
            if created:
                print(f"\nCreated {len(created)} anomaly decision(s).")
            else:
                print("\nNo new anomaly decisions created (all deduplicated or no anomalies).")
        finally:
            conn2.close()

    if args.check:
        has_issues = summary["overall_status"] != "healthy"
        sys.exit(1 if has_issues else 0)


if __name__ == "__main__":
    main()
