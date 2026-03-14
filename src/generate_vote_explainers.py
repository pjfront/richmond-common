"""
Generate vote explainers for council motions (S3.2).

Queries motions with votes from the database and generates contextual
explanations. Processes motions missing explainers by default,
oldest meetings first.

Usage:
  python generate_vote_explainers.py                        # All motions missing explainers
  python generate_vote_explainers.py --meeting-id UUID      # Single meeting
  python generate_vote_explainers.py --limit 10             # Process N motions
  python generate_vote_explainers.py --dry-run              # Show motions without generating
  python generate_vote_explainers.py --force                # Regenerate existing explainers
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load .env from repo root
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from db import get_connection, RICHMOND_FIPS  # noqa: E402
from vote_explainer import (  # noqa: E402
    generate_vote_explainer,
    should_explain,
)


# ── Database Queries ─────────────────────────────────────────


def get_motions_needing_explainers(
    conn,
    city_fips: str = RICHMOND_FIPS,
    *,
    meeting_id: str | None = None,
    force: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Get motions that need vote explainers, with their agenda item and vote context.

    Returns motions ordered by meeting date (oldest first for backfill).
    Each result includes the agenda item context and individual votes.
    """
    conditions = ["m.city_fips = %s"]
    params: list[Any] = [city_fips]

    if not force:
        conditions.append("mo.vote_explainer IS NULL")

    if meeting_id:
        conditions.append("m.id = %s")
        params.append(meeting_id)

    # Only motions that actually have votes
    conditions.append("""EXISTS (
        SELECT 1 FROM votes v WHERE v.motion_id = mo.id
    )""")

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT mo.id AS motion_id,
               mo.motion_text, mo.motion_type, mo.moved_by, mo.seconded_by,
               mo.result, mo.vote_tally, mo.sequence_number,
               ai.id AS agenda_item_id, ai.title AS item_title,
               ai.description AS item_description, ai.category,
               ai.department, ai.financial_amount, ai.is_consent_calendar,
               ai.plain_language_summary,
               m.id AS meeting_id, m.meeting_date
        FROM motions mo
        JOIN agenda_items ai ON mo.agenda_item_id = ai.id
        JOIN meetings m ON ai.meeting_id = m.id
        WHERE {where_clause}
        ORDER BY m.meeting_date ASC, ai.item_number ASC, mo.sequence_number ASC
    """

    if limit:
        query += f" LIMIT {limit}"

    with conn.cursor() as cur:
        cur.execute(query, params)
        cols = [desc[0] for desc in cur.description]
        motions = [dict(zip(cols, row)) for row in cur.fetchall()]

    # Fetch votes for each motion
    if motions:
        motion_ids = [m["motion_id"] for m in motions]
        with conn.cursor() as cur:
            cur.execute(
                """SELECT motion_id, official_name, vote_choice
                   FROM votes
                   WHERE motion_id = ANY(%s)
                   ORDER BY official_name""",
                (motion_ids,),
            )
            votes_by_motion: dict[str, list[dict[str, str]]] = {}
            for row in cur.fetchall():
                mid = str(row[0])
                votes_by_motion.setdefault(mid, []).append({
                    "official_name": row[1],
                    "vote_choice": row[2],
                })

        for motion in motions:
            motion["votes"] = votes_by_motion.get(str(motion["motion_id"]), [])

    return motions


def save_explainer(
    conn,
    motion_id: str,
    explainer: str,
    model: str,
) -> None:
    """Write generated vote explainer to the motions table."""
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE motions
               SET vote_explainer = %s,
                   vote_explainer_generated_at = %s,
                   vote_explainer_model = %s
               WHERE id = %s""",
            (explainer, datetime.now(timezone.utc), model, motion_id),
        )
    conn.commit()


# ── Main Pipeline ────────────────────────────────────────────


def generate_explainer_for_motion(
    conn,
    motion: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Generate a vote explainer for a single motion."""
    result: dict[str, Any] = {
        "motion_id": motion["motion_id"],
        "item_title": motion["item_title"],
        "category": motion["category"],
        "result": motion["result"],
        "vote_tally": motion["vote_tally"],
        "explainer": None,
        "model": None,
        "skipped": False,
        "reason": None,
    }

    # Check skip logic
    if not should_explain(
        category=motion["category"],
        is_consent_calendar=motion.get("is_consent_calendar", False),
        vote_tally=motion.get("vote_tally"),
        votes=motion.get("votes", []),
    ):
        result["skipped"] = True
        if motion["category"] == "procedural":
            result["reason"] = "procedural"
        else:
            result["reason"] = "unanimous_consent"
        return result

    if dry_run:
        result["skipped"] = True
        result["reason"] = "dry_run"
        return result

    explainer_result = generate_vote_explainer(
        item_title=motion["item_title"],
        category=motion.get("category"),
        department=motion.get("department"),
        financial_amount=motion.get("financial_amount"),
        plain_language_summary=motion.get("plain_language_summary"),
        motion_text=motion["motion_text"],
        motion_type=motion.get("motion_type"),
        moved_by=motion.get("moved_by"),
        seconded_by=motion.get("seconded_by"),
        result=motion["result"],
        vote_tally=motion.get("vote_tally"),
        votes=motion.get("votes", []),
    )

    result["explainer"] = explainer_result["explainer"]
    result["model"] = explainer_result["model"]

    save_explainer(
        conn,
        motion["motion_id"],
        explainer_result["explainer"],
        explainer_result["model"],
    )

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate vote explainers for council motions (S3.2)"
    )
    parser.add_argument(
        "--meeting-id", help="Process only motions from this meeting (UUID)"
    )
    parser.add_argument(
        "--limit", type=int, help="Maximum number of motions to process"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show motions that would be processed without generating",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate explainers for motions that already have them",
    )
    parser.add_argument(
        "--fips", default=RICHMOND_FIPS, help="City FIPS code"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Seconds to wait between API calls (default: 0.5)",
    )
    args = parser.parse_args()

    conn = get_connection()
    motions = get_motions_needing_explainers(
        conn,
        args.fips,
        meeting_id=args.meeting_id,
        force=args.force,
        limit=args.limit,
    )

    if not motions:
        print("No motions need vote explainers.")
        conn.close()
        sys.exit(0)

    # Count how many are actually explainable
    explainable = [
        m for m in motions
        if should_explain(
            category=m["category"],
            is_consent_calendar=m.get("is_consent_calendar", False),
            vote_tally=m.get("vote_tally"),
            votes=m.get("votes", []),
        )
    ]
    skippable = len(motions) - len(explainable)

    print(f"Found {len(motions)} motions ({len(explainable)} to explain, {skippable} to skip)")
    if args.dry_run:
        print("  (dry run, no API calls or DB writes)")
    if args.force:
        print("  (force mode, regenerating existing explainers)")
    print()

    generated = 0
    skipped = 0
    errors = 0
    current_date = None

    for i, motion in enumerate(motions, 1):
        meeting_date = str(motion["meeting_date"])
        if meeting_date != current_date:
            current_date = meeting_date
            print(f"\n── Meeting: {current_date} ──")

        title_preview = motion["item_title"][:60] + ("..." if len(motion["item_title"]) > 60 else "")
        tally = motion["vote_tally"] or "no tally"
        print(f"  [{i}/{len(motions)}] {title_preview} ({motion['result']}, {tally})")

        try:
            result = generate_explainer_for_motion(conn, motion, dry_run=args.dry_run)

            if result["skipped"]:
                reason = result["reason"]
                print(f"         SKIP ({reason})")
                skipped += 1
            else:
                explainer_preview = (result["explainer"] or "")[:100]
                print(f"         -> {explainer_preview}...")
                generated += 1

                # Rate limit between API calls
                if i < len(motions) and args.delay > 0:
                    time.sleep(args.delay)

        except Exception as e:
            print(f"         ERROR: {e}")
            errors += 1

    # Final tally
    print(f"\n{'='*50}")
    print(f"Done. {len(motions)} motions processed.")
    print(f"  {generated} explainers generated")
    print(f"  {skipped} skipped")
    if errors:
        print(f"  {errors} errors")
    print(f"{'='*50}")

    conn.close()


if __name__ == "__main__":
    main()
