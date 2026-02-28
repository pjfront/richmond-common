"""
Generate AI-powered bios for current council members.

Queries voting statistics, attendance, and category data from the database,
then runs the two-layer bio generator:
- Layer 1 (Factual): Pure data aggregation, no AI, public tier
- Layer 2 (Summary): AI-synthesized narrative, graduated tier

Usage:
  python generate_bios.py                  # All current officials
  python generate_bios.py --name "Martinez" # Single official (partial match)
  python generate_bios.py --dry-run        # Show stats without writing to DB
  python generate_bios.py --factual-only   # Skip Layer 2 (no API call)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load .env from repo root
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from db import get_connection, RICHMOND_FIPS  # noqa: E402
from bio_generator import build_factual_profile, generate_bio_summary  # noqa: E402


# ── Database Queries ─────────────────────────────────────────


def get_current_officials(conn, city_fips: str = RICHMOND_FIPS) -> list[dict[str, Any]]:
    """Get all current officials for the city."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, name, role, seat, term_start, term_end
               FROM officials
               WHERE city_fips = %s AND is_current = TRUE
               ORDER BY name""",
            (city_fips,),
        )
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_vote_count(conn, official_id: str) -> int:
    """Count total votes cast by an official."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM votes WHERE official_id = %s",
            (official_id,),
        )
        return cur.fetchone()[0]


def get_attendance_stats(conn, official_id: str) -> dict[str, int]:
    """Get meetings attended vs total for an official."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT
                 COUNT(*) AS total,
                 COUNT(*) FILTER (WHERE status IN ('present', 'late')) AS attended
               FROM meeting_attendance
               WHERE official_id = %s""",
            (official_id,),
        )
        row = cur.fetchone()
        return {"meetings_total": row[0], "meetings_attended": row[1]}


def get_top_categories(conn, official_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """Get top vote categories for an official.

    Joins votes -> motions -> agenda_items to get the category.
    """
    with conn.cursor() as cur:
        cur.execute(
            """SELECT ai.category, COUNT(*) AS cnt
               FROM votes v
               JOIN motions m ON v.motion_id = m.id
               JOIN agenda_items ai ON m.agenda_item_id = ai.id
               WHERE v.official_id = %s
                 AND ai.category IS NOT NULL
                 AND ai.category != 'procedural'
               GROUP BY ai.category
               ORDER BY cnt DESC
               LIMIT %s""",
            (official_id, limit),
        )
        return [{"category": row[0], "count": row[1]} for row in cur.fetchall()]


def get_majority_alignment_rate(conn, official_id: str) -> float:
    """Calculate how often this official votes with the majority.

    For each motion where this official voted, determine the majority outcome
    (the vote_choice with the most votes, excluding 'absent'), then check
    if this official's vote matches.

    Returns a float between 0.0 and 1.0.
    """
    with conn.cursor() as cur:
        cur.execute(
            """WITH official_votes AS (
                 -- All votes cast by this official (excluding absent)
                 SELECT v.motion_id, v.vote_choice
                 FROM votes v
                 WHERE v.official_id = %s
                   AND v.vote_choice != 'absent'
               ),
               majority_per_motion AS (
                 -- For each motion, find the majority vote choice
                 SELECT DISTINCT ON (v.motion_id)
                   v.motion_id,
                   v.vote_choice AS majority_choice
                 FROM votes v
                 WHERE v.vote_choice != 'absent'
                   AND v.motion_id IN (SELECT motion_id FROM official_votes)
                 GROUP BY v.motion_id, v.vote_choice
                 ORDER BY v.motion_id, COUNT(*) DESC
               )
               SELECT
                 COUNT(*) AS total_votes,
                 COUNT(*) FILTER (
                   WHERE ov.vote_choice = mpm.majority_choice
                 ) AS with_majority
               FROM official_votes ov
               JOIN majority_per_motion mpm ON ov.motion_id = mpm.motion_id""",
            (official_id,),
        )
        row = cur.fetchone()
        total, with_majority = row[0], row[1]
        if total == 0:
            return 0.0
        return with_majority / total


def get_sole_dissent_stats(conn, official_id: str) -> dict[str, Any]:
    """Find motions where this official was the sole dissenter.

    A sole dissent is when the official voted 'nay' and every other
    non-absent voter on that motion voted 'aye' (or vice versa: sole 'aye'
    against all 'nay').

    Returns count and category breakdown.
    """
    with conn.cursor() as cur:
        cur.execute(
            """WITH official_votes AS (
                 -- This official's non-absent votes
                 SELECT v.motion_id, v.vote_choice
                 FROM votes v
                 WHERE v.official_id = %s
                   AND v.vote_choice NOT IN ('absent', 'abstain')
               ),
               motion_tallies AS (
                 -- For each motion where this official voted,
                 -- count how many others voted the same vs different
                 SELECT
                   ov.motion_id,
                   ov.vote_choice AS official_choice,
                   COUNT(*) FILTER (
                     WHERE v.vote_choice = ov.vote_choice
                       AND v.official_id != %s
                   ) AS same_count,
                   COUNT(*) FILTER (
                     WHERE v.vote_choice != ov.vote_choice
                       AND v.vote_choice NOT IN ('absent', 'abstain')
                       AND v.official_id != %s
                   ) AS different_count
                 FROM official_votes ov
                 JOIN votes v ON v.motion_id = ov.motion_id
                 WHERE v.vote_choice NOT IN ('absent', 'abstain')
                 GROUP BY ov.motion_id, ov.vote_choice
               ),
               sole_dissents AS (
                 -- Sole dissent: nobody else voted the same way
                 SELECT mt.motion_id
                 FROM motion_tallies mt
                 WHERE mt.same_count = 0 AND mt.different_count > 0
               )
               SELECT ai.category, COUNT(*) AS cnt
               FROM sole_dissents sd
               JOIN motions m ON m.id = sd.motion_id
               JOIN agenda_items ai ON ai.id = m.agenda_item_id
               WHERE ai.category IS NOT NULL
               GROUP BY ai.category
               ORDER BY cnt DESC""",
            (official_id, official_id, official_id),
        )
        categories = [{"category": row[0], "count": row[1]} for row in cur.fetchall()]
        total_count = sum(c["count"] for c in categories)
        return {
            "sole_dissent_count": total_count,
            "sole_dissent_categories": categories,
        }


def save_official_bios(
    conn,
    official_id: str,
    bio_factual: dict[str, Any],
    bio_summary: str | None = None,
    bio_model: str | None = None,
) -> None:
    """Write generated bio data to the officials table."""
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE officials
               SET bio_factual = %s,
                   bio_summary = %s,
                   bio_generated_at = %s,
                   bio_model = %s
               WHERE id = %s""",
            (
                json.dumps(bio_factual),
                bio_summary,
                datetime.now(timezone.utc),
                bio_model,
                official_id,
            ),
        )
    conn.commit()


# ── Main Pipeline ────────────────────────────────────────────


def generate_bio_for_official(
    conn,
    official: dict[str, Any],
    *,
    factual_only: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Generate bio for a single official. Returns the results dict."""
    oid = str(official["id"])
    name = official["name"]

    # Gather stats
    vote_count = get_vote_count(conn, oid)
    attendance = get_attendance_stats(conn, oid)
    alignment = get_majority_alignment_rate(conn, oid)
    dissent = get_sole_dissent_stats(conn, oid)

    # Layer 1: Factual profile
    factual = build_factual_profile(
        official_name=name,
        official_role=official["role"],
        official_seat=official.get("seat"),
        term_start=str(official["term_start"]) if official.get("term_start") else None,
        term_end=str(official["term_end"]) if official.get("term_end") else None,
        vote_count=vote_count,
        meetings_attended=attendance["meetings_attended"],
        meetings_total=attendance["meetings_total"],
        majority_alignment_rate=alignment,
        sole_dissent_count=dissent["sole_dissent_count"],
        sole_dissent_categories=dissent["sole_dissent_categories"],
    )

    result = {
        "name": name,
        "vote_count": vote_count,
        "attendance": attendance,
        "alignment_rate": f"{round(alignment * 100)}%",
        "sole_dissent_count": dissent["sole_dissent_count"],
        "factual_profile": factual,
        "summary": None,
        "model": None,
    }

    # Layer 2: AI summary (optional)
    if not factual_only and vote_count > 0:
        try:
            summary_result = generate_bio_summary(factual)
            result["summary"] = summary_result["summary"]
            result["model"] = summary_result["model"]
        except Exception as e:
            print(f"  WARNING: Layer 2 generation failed for {name}: {e}")

    # Write to DB
    if not dry_run:
        save_official_bios(
            conn,
            oid,
            bio_factual=factual,
            bio_summary=result["summary"],
            bio_model=result["model"],
        )

    return result


def main():
    parser = argparse.ArgumentParser(description="Generate bios for council members")
    parser.add_argument("--name", help="Filter to official matching this name (partial match)")
    parser.add_argument("--dry-run", action="store_true", help="Show stats without writing to DB")
    parser.add_argument("--factual-only", action="store_true", help="Skip AI summary (Layer 2)")
    parser.add_argument("--fips", default=RICHMOND_FIPS, help="City FIPS code")
    args = parser.parse_args()

    conn = get_connection()
    officials = get_current_officials(conn, args.fips)

    if args.name:
        search = args.name.lower()
        officials = [o for o in officials if search in o["name"].lower()]
        if not officials:
            print(f"No current officials matching '{args.name}'")
            sys.exit(1)

    print(f"Generating bios for {len(officials)} official(s)...")
    if args.dry_run:
        print("  (dry run, no DB writes)")
    if args.factual_only:
        print("  (factual only, no AI summary)")
    print()

    results = []
    for official in officials:
        name = official["name"]
        print(f"── {name} ({official['role']}) ──")

        result = generate_bio_for_official(
            conn,
            official,
            factual_only=args.factual_only,
            dry_run=args.dry_run,
        )
        results.append(result)

        # Print summary
        print(f"  Votes: {result['vote_count']}")
        att = result["attendance"]
        print(f"  Attendance: {att['meetings_attended']}/{att['meetings_total']}")
        print(f"  Majority alignment: {result['alignment_rate']}")
        print(f"  Sole dissents: {result['sole_dissent_count']}")
        if result["summary"]:
            print(f"  Summary: {result['summary'][:120]}...")
        elif result["vote_count"] == 0:
            print("  (no votes on record, skipping summary)")
        print()

    # Final tally
    written = [r for r in results if not args.dry_run]
    skipped = [r for r in results if r["vote_count"] == 0]
    with_summary = [r for r in results if r["summary"]]

    print(f"Done. {len(results)} officials processed.")
    if not args.dry_run:
        print(f"  {len(written)} bios written to DB")
    print(f"  {len(with_summary)} with AI summaries")
    if skipped:
        print(f"  {len(skipped)} skipped (no vote data)")

    conn.close()


if __name__ == "__main__":
    main()
