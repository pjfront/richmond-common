"""
Generate plain language summaries for agenda items.

Queries agenda items from the database and generates plain English
summaries and headlines. Processes items missing summaries by default,
oldest meetings first.

Usage:
  python generate_summaries.py                        # All items missing summaries
  python generate_summaries.py --meeting-id UUID      # Single meeting
  python generate_summaries.py --limit 10             # Process N items
  python generate_summaries.py --dry-run              # Show items without generating
  python generate_summaries.py --force                # Regenerate existing summaries
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
from dotenv import load_dotenv

# Load .env from repo root
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from db import get_connection, RICHMOND_FIPS  # noqa: E402
from plain_language_summarizer import (  # noqa: E402
    generate_plain_language_summary,
    should_summarize,
)


# ── Database Queries ─────────────────────────────────────────


def get_items_needing_summaries(
    conn,
    city_fips: str = RICHMOND_FIPS,
    *,
    meeting_id: str | None = None,
    force: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Get agenda items that need plain language summaries.

    Returns items ordered by meeting date (oldest first for backfill).
    """
    conditions = ["m.city_fips = %s"]
    params: list[Any] = [city_fips]

    if not force:
        conditions.append("ai.plain_language_summary IS NULL")

    if meeting_id:
        conditions.append("ai.meeting_id = %s")
        params.append(meeting_id)

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT ai.id, ai.title, ai.description, ai.category,
               ai.department, ai.financial_amount, ai.item_number,
               m.meeting_date
        FROM agenda_items ai
        JOIN meetings m ON ai.meeting_id = m.id
        WHERE {where_clause}
        ORDER BY m.meeting_date ASC, ai.item_number ASC
    """

    if limit:
        query += f" LIMIT {limit}"

    with conn.cursor() as cur:
        cur.execute(query, params)
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def save_summary(
    conn,
    item_id: str,
    summary: str,
    headline: str | None,
    model: str,
) -> None:
    """Write generated summary and headline to the agenda_items table."""
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE agenda_items
               SET plain_language_summary = %s,
                   summary_headline = %s,
                   plain_language_generated_at = %s,
                   plain_language_model = %s
               WHERE id = %s""",
            (summary, headline, datetime.now(timezone.utc), model, item_id),
        )
    conn.commit()


# ── Connection Helpers ───────────────────────────────────────


def _reconnect(conn) -> Any:
    """Close a dead connection and return a fresh one."""
    try:
        conn.close()
    except Exception:
        pass
    print("  ↻ Reconnecting to database...")
    return get_connection()


# ── Main Pipeline ────────────────────────────────────────────


def generate_summary_for_item(
    conn,
    item: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Generate a plain language summary for a single agenda item."""
    result: dict[str, Any] = {
        "id": item["id"],
        "title": item["title"],
        "category": item["category"],
        "summary": None,
        "headline": None,
        "model": None,
        "skipped": False,
        "reason": None,
    }

    # Skip procedural items
    if not should_summarize(item["category"]):
        result["skipped"] = True
        result["reason"] = "procedural"
        return result

    # Skip items with insufficient content to summarize meaningfully
    title_text = (item.get("title") or "").strip()
    description_text = (item.get("description") or "").strip()
    if len(f"{title_text} {description_text}".strip()) < 20:
        result["skipped"] = True
        result["reason"] = "insufficient_content"
        return result

    if dry_run:
        result["skipped"] = True
        result["reason"] = "dry_run"
        return result

    summary_result = generate_plain_language_summary(
        title=item["title"],
        description=item.get("description"),
        category=item.get("category"),
        department=item.get("department"),
        financial_amount=item.get("financial_amount"),
        staff_report=item.get("staff_report"),
    )

    result["summary"] = summary_result["summary"]
    result["headline"] = summary_result["headline"]
    result["model"] = summary_result["model"]

    save_summary(
        conn,
        item["id"],
        summary_result["summary"],
        summary_result["headline"],
        summary_result["model"],
    )

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate plain language summaries for agenda items"
    )
    parser.add_argument(
        "--meeting-id", help="Process only items from this meeting (UUID)"
    )
    parser.add_argument(
        "--limit", type=int, help="Maximum number of items to process"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show items that would be processed without generating",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate summaries for items that already have them",
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
    items = get_items_needing_summaries(
        conn,
        args.fips,
        meeting_id=args.meeting_id,
        force=args.force,
        limit=args.limit,
    )

    if not items:
        print("No agenda items need summaries.")
        conn.close()
        sys.exit(0)

    # Count how many are actually summarizable (non-procedural)
    summarizable = [i for i in items if should_summarize(i["category"])]
    procedural = len(items) - len(summarizable)

    print(f"Found {len(items)} items ({len(summarizable)} to summarize, {procedural} procedural to skip)")
    if args.dry_run:
        print("  (dry run, no API calls or DB writes)")
    if args.force:
        print("  (force mode, regenerating existing summaries)")
    print()

    generated = 0
    skipped = 0
    errors = 0
    current_date = None

    for i, item in enumerate(items, 1):
        meeting_date = str(item["meeting_date"])
        if meeting_date != current_date:
            current_date = meeting_date
            print(f"\n── Meeting: {current_date} ──")

        title_preview = item["title"][:70] + ("..." if len(item["title"]) > 70 else "")
        print(f"  [{i}/{len(items)}] {item['item_number']}: {title_preview}")

        try:
            result = generate_summary_for_item(conn, item, dry_run=args.dry_run)

            if result["skipped"]:
                reason = result["reason"]
                print(f"         SKIP ({reason})")
                skipped += 1
            else:
                summary_preview = (result["summary"] or "")[:80]
                headline_preview = (result["headline"] or "(no headline)")[:60]
                print(f"         → {headline_preview}")
                print(f"           {summary_preview}...")
                generated += 1

                # Rate limit between API calls
                if i < len(items) and args.delay > 0:
                    time.sleep(args.delay)

        except (psycopg2.InterfaceError, psycopg2.OperationalError) as e:
            # DB connection dropped mid-run — reconnect and retry this item once
            print(f"         DB connection lost ({e})")
            conn = _reconnect(conn)
            try:
                result = generate_summary_for_item(conn, item, dry_run=args.dry_run)
                if result["skipped"]:
                    print(f"         SKIP ({result['reason']})")
                    skipped += 1
                else:
                    print(f"         → {(result['headline'] or '(no headline)')[:60]}")
                    print(f"           {(result['summary'] or '')[:80]}...")
                    generated += 1
                    if i < len(items) and args.delay > 0:
                        time.sleep(args.delay)
            except Exception as retry_e:
                print(f"         ERROR after reconnect: {retry_e}")
                errors += 1

        except Exception as e:
            print(f"         ERROR: {e}")
            errors += 1

    # Final tally
    print(f"\n{'='*50}")
    print(f"Done. {len(items)} items processed.")
    print(f"  {generated} summaries generated")
    print(f"  {skipped} skipped")
    if errors:
        print(f"  {errors} errors")
    print(f"{'='*50}")

    conn.close()


if __name__ == "__main__":
    main()
