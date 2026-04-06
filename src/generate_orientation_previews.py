"""
Generate pre-meeting orientation previews from agenda item data.

Produces a 3-5 paragraph narrative preview for each meeting, stored in
meetings.orientation_preview. Uses agenda items' headlines, categories,
financial amounts, and topic labels — plus historical topic recurrence —
to create a forward-looking "what to watch for" briefing.

Unlike meeting_summary (which requires votes/minutes), orientations can
be generated immediately when agenda items are scraped from eSCRIBE.

Usage:
    python generate_orientation_previews.py                  # all ungenerated
    python generate_orientation_previews.py --limit 10       # first 10
    python generate_orientation_previews.py --meeting-id X   # specific meeting
    python generate_orientation_previews.py --force           # regenerate all
    python generate_orientation_previews.py --dry-run         # preview without saving

Publication tier: Public (factual presentation of published agenda data).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(filename: str) -> str:
    path = _PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text().strip()


# ── Agenda items query (no vote data — pre-meeting) ──────────────────

_AGENDA_ITEMS_QUERY = """
    SELECT
        ai.item_number,
        ai.title,
        ai.summary_headline,
        ai.plain_language_summary,
        ai.category,
        ai.financial_amount,
        ai.is_consent_calendar,
        ai.department,
        ai.topic_label,
        ai.continued_from
    FROM agenda_items ai
    WHERE ai.meeting_id = %s
    AND ai.category != 'procedural'
    ORDER BY ai.item_number
"""

# ── Historical topic recurrence (past 12 months) ─────────────────────

_TOPIC_HISTORY_QUERY = """
    SELECT
        ai2.topic_label,
        COUNT(DISTINCT ai2.meeting_id) as meeting_count,
        MAX(m2.meeting_date) as most_recent
    FROM agenda_items ai2
    JOIN meetings m2 ON m2.id = ai2.meeting_id
    WHERE ai2.topic_label IN (
        SELECT DISTINCT topic_label FROM agenda_items
        WHERE meeting_id = %s AND topic_label IS NOT NULL
    )
    AND m2.city_fips = %s
    AND m2.meeting_date < %s
    AND m2.meeting_date > %s::date - interval '12 months'
    AND ai2.meeting_id != %s
    GROUP BY ai2.topic_label
    HAVING COUNT(DISTINCT ai2.meeting_id) >= 2
"""

# ── Continuation resolution ──────────────────────────────────────────

_CONTINUATION_QUERY = """
    SELECT m.meeting_date
    FROM agenda_items ai
    JOIN meetings m ON m.id = ai.meeting_id
    WHERE ai.meeting_id != %s
    AND ai.item_number = %s
    AND m.city_fips = %s
    AND m.meeting_date < %s
    ORDER BY m.meeting_date DESC
    LIMIT 1
"""


def _fetch_items(cur, meeting_id: str) -> list[dict]:
    """Fetch agenda items for a single meeting (no vote data)."""
    cur.execute(_AGENDA_ITEMS_QUERY, (meeting_id,))
    return [
        {
            "item_number": row[0],
            "title": row[1],
            "summary_headline": row[2],
            "plain_language_summary": row[3],
            "category": row[4],
            "financial_amount": row[5],
            "is_consent_calendar": row[6],
            "department": row[7],
            "topic_label": row[8],
            "continued_from": row[9],
        }
        for row in cur.fetchall()
    ]


def _fetch_topic_history(
    cur, meeting_id: str, meeting_date: str, city_fips: str,
) -> dict[str, dict]:
    """Fetch historical recurrence data for topics in this meeting."""
    cur.execute(
        _TOPIC_HISTORY_QUERY,
        (meeting_id, city_fips, meeting_date, meeting_date, meeting_id),
    )
    return {
        row[0]: {"meeting_count": row[1], "most_recent": str(row[2])}
        for row in cur.fetchall()
    }


def _resolve_continuation(
    cur, meeting_id: str, continued_from: str, city_fips: str, meeting_date: str,
) -> str | None:
    """Resolve a continued_from reference to a meeting date."""
    cur.execute(
        _CONTINUATION_QUERY,
        (meeting_id, continued_from, city_fips, meeting_date),
    )
    row = cur.fetchone()
    return str(row[0]) if row else None


def _build_orientation_context(
    items: list[dict],
    topic_history: dict[str, dict],
    continuations: dict[str, str],
) -> str:
    """Build structured text block for the LLM.

    Includes agenda items grouped by consent vs action, plus HISTORY
    and CONTINUATION annotations for recurring/continued items.
    """
    lines = []
    consent_items = []
    action_items = []

    for item in items:
        if item.get("is_consent_calendar"):
            consent_items.append(item)
        else:
            action_items.append(item)

    if consent_items:
        lines.append(f"CONSENT CALENDAR ({len(consent_items)} items):")
        for item in consent_items[:15]:
            headline = item.get("summary_headline") or item.get("title", "")
            amount = item.get("financial_amount")
            line = f"  - {headline}"
            if amount:
                line += f" ({amount})"
            topic = item.get("topic_label")
            if topic and topic in topic_history:
                h = topic_history[topic]
                line += f" [recurring topic: {h['meeting_count']} past meetings]"
            lines.append(line)
        if len(consent_items) > 15:
            lines.append(f"  - ... and {len(consent_items) - 15} more routine items")

    if action_items:
        lines.append(f"\nACTION ITEMS ({len(action_items)} items):")
        for item in action_items:
            headline = item.get("summary_headline") or item.get("title", "")
            category = item.get("category", "")
            amount = item.get("financial_amount")
            department = item.get("department", "")
            topic = item.get("topic_label")
            summary = item.get("plain_language_summary", "")

            line = f"  - [{category}] {headline}"
            if amount:
                line += f" ({amount})"
            if department:
                line += f" [dept: {department}]"
            lines.append(line)

            # Add plain language summary if available (truncated)
            if summary:
                truncated = summary[:200] + "..." if len(summary) > 200 else summary
                lines.append(f"    Summary: {truncated}")

    # Inject historical context
    history_lines = []
    for topic, data in topic_history.items():
        from datetime import datetime
        most_recent = data["most_recent"]
        try:
            recent_dt = datetime.strptime(most_recent, "%Y-%m-%d")
            recent_str = recent_dt.strftime("%B %d, %Y")
        except (ValueError, TypeError):
            recent_str = most_recent
        history_lines.append(
            f'HISTORY: "{topic}" has appeared on {data["meeting_count"]} '
            f"agendas in the past 12 months (most recently {recent_str})"
        )

    if history_lines:
        lines.append("\n" + "\n".join(history_lines))

    # Inject continuation context
    for item_number, continued_date in continuations.items():
        try:
            from datetime import datetime
            dt = datetime.strptime(continued_date, "%Y-%m-%d")
            date_str = dt.strftime("%B %d, %Y")
        except (ValueError, TypeError):
            date_str = continued_date
        lines.append(f"CONTINUATION: Item {item_number} was continued from the {date_str} meeting.")

    return "\n".join(lines)


def _parse_orientation(text: str) -> str | None:
    """Parse JSON response to extract orientation_preview."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1:]
        if text.endswith("```"):
            text = text[:-3].strip()

    try:
        data = json.loads(text)
        return (data.get("orientation_preview") or "").strip() or None
    except (json.JSONDecodeError, AttributeError):
        # Last resort: try to extract orientation_preview from partial JSON
        if '"orientation_preview"' in text:
            try:
                import re
                match = re.search(r'"orientation_preview"\s*:\s*"(.*)"', text, re.DOTALL)
                if match:
                    # Unescape JSON string
                    raw_val = match.group(1)
                    return raw_val.replace("\\n", "\n").strip() or None
            except Exception:
                pass
        logger.warning("Failed to parse JSON, using raw text")
        return text.strip() or None


def generate_orientation(
    items: list[dict],
    topic_history: dict[str, dict],
    continuations: dict[str, str],
) -> dict[str, str | None]:
    """Generate a pre-meeting orientation from agenda item data.

    Returns dict with 'orientation_preview' and 'model' keys.
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic package required for orientation generation")

    system_prompt = _load_prompt("orientation_preview_system.txt")
    context = _build_orientation_context(items, topic_history, continuations)

    if not context.strip():
        return {"orientation_preview": None, "model": None}

    user_prompt = f"Write a pre-meeting orientation for this city council agenda:\n\n{context}"

    client = anthropic.Anthropic(timeout=60.0)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=800,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    preview = _parse_orientation(response.content[0].text)
    return {"orientation_preview": preview, "model": response.model}


def generate_previews(
    conn,
    city_fips: str = "0660620",
    force: bool = False,
    meeting_id: str | None = None,
    limit: int | None = None,
    delay: float = 0.5,
) -> dict:
    """Generate orientation previews. Callable from data_sync or CLI.

    Returns dict with 'total', 'generated', 'skipped', 'errors' counts.
    """
    stats = {"total": 0, "generated": 0, "skipped": 0, "errors": 0}

    with conn.cursor() as cur:
        # No vote gate — orientation generates from agenda data alone
        if meeting_id:
            cur.execute(
                "SELECT m.id, m.meeting_date, m.meeting_type FROM meetings m "
                "WHERE m.id = %s",
                (meeting_id,),
            )
        elif force:
            cur.execute(
                "SELECT m.id, m.meeting_date, m.meeting_type FROM meetings m "
                "WHERE m.city_fips = %s "
                "ORDER BY m.meeting_date DESC",
                (city_fips,),
            )
        else:
            cur.execute(
                "SELECT m.id, m.meeting_date, m.meeting_type FROM meetings m "
                "WHERE m.city_fips = %s AND m.orientation_preview IS NULL "
                "ORDER BY m.meeting_date DESC",
                (city_fips,),
            )

        meetings = cur.fetchall()
        if limit:
            meetings = meetings[:limit]

        stats["total"] = len(meetings)
        logger.info(f"Found {len(meetings)} meetings to generate orientations for")

        for mid, meeting_date, meeting_type in meetings:
            items = _fetch_items(cur, mid)

            if not items:
                logger.info(f"  {meeting_date} ({meeting_type}): no non-procedural items, skipping")
                stats["skipped"] += 1
                continue

            # Fetch historical context
            topic_history = _fetch_topic_history(cur, mid, str(meeting_date), city_fips)

            # Resolve continuations
            continuations = {}
            for item in items:
                cf = item.get("continued_from")
                if cf:
                    resolved = _resolve_continuation(
                        cur, mid, cf, city_fips, str(meeting_date),
                    )
                    if resolved:
                        continuations[item["item_number"]] = resolved

            logger.info(
                f"  {meeting_date} ({meeting_type}): {len(items)} items, "
                f"{len(topic_history)} recurring topics, "
                f"{len(continuations)} continuations"
            )

            try:
                result = generate_orientation(items, topic_history, continuations)
                if result["orientation_preview"]:
                    cur.execute(
                        "UPDATE meetings SET orientation_preview = %s WHERE id = %s",
                        (result["orientation_preview"], mid),
                    )
                    conn.commit()
                    logger.info(f"    Saved orientation ({len(result['orientation_preview'])} chars)")
                    stats["generated"] += 1
                else:
                    logger.warning(f"    No orientation generated")
                    stats["skipped"] += 1
            except Exception as e:
                logger.error(f"    Error: {e}")
                conn.rollback()
                stats["errors"] += 1

            if delay > 0:
                time.sleep(delay)

    logger.info(f"Done. Generated {stats['generated']}/{stats['total']} orientations.")
    return stats


def main():
    parser = argparse.ArgumentParser(description="Generate pre-meeting orientation previews")
    parser.add_argument("--limit", type=int, help="Max meetings to process")
    parser.add_argument("--meeting-id", help="Process specific meeting")
    parser.add_argument("--force", action="store_true", help="Regenerate existing orientations")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between API calls (seconds)")
    args = parser.parse_args()

    import psycopg2

    conn = psycopg2.connect(os.environ["DATABASE_URL"])

    try:
        if args.dry_run:
            with conn.cursor() as cur:
                if args.meeting_id:
                    cur.execute(
                        "SELECT m.id, m.meeting_date, m.meeting_type FROM meetings m "
                        "WHERE m.id = %s",
                        (args.meeting_id,),
                    )
                else:
                    cur.execute(
                        "SELECT m.id, m.meeting_date, m.meeting_type FROM meetings m "
                        "WHERE m.city_fips = '0660620' AND m.orientation_preview IS NULL "
                        "ORDER BY m.meeting_date DESC",
                    )
                meetings = cur.fetchall()
                if args.limit:
                    meetings = meetings[:args.limit]
                logger.info(f"Found {len(meetings)} meetings to generate orientations for")
                for mid, meeting_date, meeting_type in meetings:
                    items = _fetch_items(cur, mid)
                    topic_history = _fetch_topic_history(cur, mid, str(meeting_date), "0660620")
                    continuations = {}
                    for item in items:
                        cf = item.get("continued_from")
                        if cf:
                            resolved = _resolve_continuation(
                                cur, mid, cf, "0660620", str(meeting_date),
                            )
                            if resolved:
                                continuations[item["item_number"]] = resolved
                    context = _build_orientation_context(items, topic_history, continuations)
                    print(f"\n--- {meeting_date} ({meeting_type}) ---")
                    print(f"  {len(items)} items, {len(topic_history)} recurring, {len(continuations)} continued")
                    print(context[:800])
                    if len(context) > 800:
                        print("...")
        else:
            generate_previews(
                conn,
                force=args.force,
                meeting_id=args.meeting_id,
                limit=args.limit,
                delay=args.delay,
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
