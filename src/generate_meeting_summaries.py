"""
Generate meeting-level summaries from agenda item data.

Produces a 3-5 bullet narrative summary for each meeting, stored in
meetings.meeting_summary. Uses the agenda items' headlines, categories,
financial amounts, and vote outcomes to create a concise overview.

Usage:
    python generate_meeting_summaries.py                  # all unsummarized
    python generate_meeting_summaries.py --limit 10       # first 10
    python generate_meeting_summaries.py --meeting-id X   # specific meeting
    python generate_meeting_summaries.py --force           # regenerate all
    python generate_meeting_summaries.py --dry-run         # preview without saving

Publication tier: Graduated (AI-generated content, operator review before public).
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


def _build_meeting_context(items: list[dict]) -> str:
    """Build a structured text block from agenda items for the LLM.

    Vote outcomes are explicit: every item shows PASSED, FAILED, or NO VOTE.
    This prevents the LLM from guessing outcomes based on agenda titles.
    """
    lines = []
    consent_items = []
    action_items = []

    for item in items:
        if item.get("is_consent_calendar"):
            consent_items.append(item)
        else:
            action_items.append(item)

    # Consent calendar: typically passed as a block
    consent_result = ""
    if consent_items:
        # Check if consent items have vote data
        has_consent_votes = any(i.get("vote_result") for i in consent_items)
        if has_consent_votes:
            consent_result = " — PASSED as a block"
        lines.append(f"CONSENT CALENDAR ({len(consent_items)} items){consent_result}:")
        for item in consent_items[:15]:  # Cap to avoid token overflow
            headline = item.get("summary_headline") or item.get("title", "")
            amount = item.get("financial_amount")
            line = f"  - {headline}"
            if amount:
                line += f" ({amount})"
            lines.append(line)
        if len(consent_items) > 15:
            lines.append(f"  - ... and {len(consent_items) - 15} more routine items")

    if action_items:
        # Sort by controversy: most comments + nay votes first
        action_items.sort(
            key=lambda i: (i.get("comment_count", 0) + i.get("nay_count", 0) * 3),
            reverse=True,
        )
        lines.append(f"\nACTION ITEMS ({len(action_items)} items, ordered by public interest):")
        for item in action_items:
            headline = item.get("summary_headline") or item.get("title", "")
            category = item.get("category", "")
            amount = item.get("financial_amount")
            vote_result = item.get("vote_result", "")
            vote_detail = item.get("vote_detail", "")
            comments = item.get("comment_count", 0)
            nays = item.get("nay_count", 0)

            # Outcome is explicit — never omitted
            if vote_result:
                outcome = vote_result.upper()
            else:
                outcome = "NO VOTE RECORDED"

            line = f"  - [{category}] {headline}"
            if amount:
                line += f" ({amount})"
            line += f" — {outcome}"
            if vote_detail and vote_result:
                line += f" [{vote_detail}]"
            if comments > 0:
                line += f" ({comments} public comments)"
            if nays > 0:
                line += f" ({nays} nay votes)"
            lines.append(line)

    return "\n".join(lines)


def _parse_meeting_summary(text: str) -> str | None:
    """Parse JSON response to extract meeting_summary."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1:]
        if text.endswith("```"):
            text = text[:-3].strip()

    try:
        data = json.loads(text)
        return (data.get("meeting_summary") or "").strip() or None
    except (json.JSONDecodeError, AttributeError):
        logger.warning("Failed to parse JSON, using raw text")
        return text.strip() or None


def generate_meeting_summary(items: list[dict]) -> dict[str, str | None]:
    """Generate a meeting-level summary from agenda item data.

    Returns dict with 'meeting_summary' and 'model' keys.
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic package required for summary generation")

    system_prompt = _load_prompt("meeting_summary_system.txt")
    context = _build_meeting_context(items)

    if not context.strip():
        return {"meeting_summary": None, "model": None}

    user_prompt = f"Summarize this city council meeting:\n\n{context}"

    client = anthropic.Anthropic(timeout=60.0)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=400,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    summary = _parse_meeting_summary(response.content[0].text)
    return {"meeting_summary": summary, "model": response.model}


_AGENDA_ITEMS_QUERY = """
    SELECT
        ai.title,
        ai.summary_headline,
        ai.category,
        ai.financial_amount,
        ai.is_consent_calendar,
        COALESCE(
            (SELECT CASE WHEN LOWER(m.result) = 'passed' THEN 'Passed'
                        WHEN LOWER(m.result) = 'failed' THEN 'Failed'
                        ELSE '' END
             FROM motions m
             WHERE m.agenda_item_id = ai.id
             AND m.result IS NOT NULL
             ORDER BY m.sequence_number DESC NULLS LAST, m.created_at DESC
             LIMIT 1),
            ''
        ) as vote_result,
        (
            SELECT string_agg(
                v.official_name || ': ' || v.vote_choice, ', '
                ORDER BY v.official_name
            )
            FROM votes v
            WHERE v.motion_id = (
                SELECT m.id FROM motions m
                WHERE m.agenda_item_id = ai.id
                AND m.result IS NOT NULL
                ORDER BY m.sequence_number DESC NULLS LAST, m.created_at DESC
                LIMIT 1
            )
        ) as vote_detail,
        (
            SELECT COUNT(*) FROM public_comments pc
            WHERE pc.agenda_item_id = ai.id
        ) as comment_count,
        (
            SELECT COUNT(*)
            FROM votes v
            WHERE v.motion_id = (
                SELECT m.id FROM motions m
                WHERE m.agenda_item_id = ai.id
                AND m.result IS NOT NULL
                ORDER BY m.sequence_number DESC NULLS LAST, m.created_at DESC
                LIMIT 1
            )
            AND v.vote_choice = 'nay'
        ) as nay_count
    FROM agenda_items ai
    WHERE ai.meeting_id = %s
    AND ai.category != 'procedural'
    ORDER BY ai.item_number
"""

_VOTE_GATE = """
    AND EXISTS (
        SELECT 1 FROM agenda_items ai2
        JOIN motions mo ON mo.agenda_item_id = ai2.id
        WHERE ai2.meeting_id = m.id
    )
"""


def _fetch_items(cur, meeting_id: str) -> list[dict]:
    """Fetch agenda items with vote outcomes for a single meeting."""
    cur.execute(_AGENDA_ITEMS_QUERY, (meeting_id,))
    return [
        {
            "title": row[0],
            "summary_headline": row[1],
            "category": row[2],
            "financial_amount": row[3],
            "is_consent_calendar": row[4],
            "vote_result": row[5] or "",
            "vote_detail": row[6] or "",
            "comment_count": row[7] or 0,
            "nay_count": row[8] or 0,
        }
        for row in cur.fetchall()
    ]


def generate_summaries(
    conn,
    city_fips: str = "0660620",
    force: bool = False,
    meeting_id: str | None = None,
    limit: int | None = None,
    delay: float = 0.5,
) -> dict:
    """Generate meeting summaries. Callable from data_sync or CLI.

    Returns dict with 'total', 'generated', 'skipped', 'errors' counts.
    """
    stats = {"total": 0, "generated": 0, "skipped": 0, "errors": 0}

    with conn.cursor() as cur:
        if meeting_id:
            cur.execute(
                "SELECT m.id, m.meeting_date, m.meeting_type FROM meetings m "
                "WHERE m.id = %s" + _VOTE_GATE,
                (meeting_id,),
            )
        elif force:
            cur.execute(
                "SELECT m.id, m.meeting_date, m.meeting_type FROM meetings m "
                "WHERE m.city_fips = %s" + _VOTE_GATE +
                " ORDER BY m.meeting_date DESC",
                (city_fips,),
            )
        else:
            cur.execute(
                "SELECT m.id, m.meeting_date, m.meeting_type FROM meetings m "
                "WHERE m.city_fips = %s AND m.meeting_summary IS NULL"
                + _VOTE_GATE +
                " ORDER BY m.meeting_date DESC",
                (city_fips,),
            )

        meetings = cur.fetchall()
        if limit:
            meetings = meetings[:limit]

        stats["total"] = len(meetings)
        logger.info(f"Found {len(meetings)} meetings to summarize")

        for mid, meeting_date, meeting_type in meetings:
            items = _fetch_items(cur, mid)

            if not items:
                logger.info(f"  {meeting_date} ({meeting_type}): no non-procedural items, skipping")
                stats["skipped"] += 1
                continue

            logger.info(f"  {meeting_date} ({meeting_type}): {len(items)} items")

            try:
                result = generate_meeting_summary(items)
                if result["meeting_summary"]:
                    cur.execute(
                        "UPDATE meetings SET meeting_summary = %s WHERE id = %s",
                        (result["meeting_summary"], mid),
                    )
                    conn.commit()
                    logger.info(f"    Saved summary ({len(result['meeting_summary'])} chars)")
                    stats["generated"] += 1
                else:
                    logger.warning(f"    No summary generated")
                    stats["skipped"] += 1
            except Exception as e:
                logger.error(f"    Error: {e}")
                conn.rollback()
                stats["errors"] += 1

            if delay > 0:
                time.sleep(delay)

    logger.info(f"Done. Processed {stats['generated']}/{stats['total']} meetings.")
    return stats


def main():
    parser = argparse.ArgumentParser(description="Generate meeting-level summaries")
    parser.add_argument("--limit", type=int, help="Max meetings to process")
    parser.add_argument("--meeting-id", help="Process specific meeting")
    parser.add_argument("--force", action="store_true", help="Regenerate existing summaries")
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
                        "WHERE m.id = %s" + _VOTE_GATE,
                        (args.meeting_id,),
                    )
                else:
                    cur.execute(
                        "SELECT m.id, m.meeting_date, m.meeting_type FROM meetings m "
                        "WHERE m.city_fips = '0660620' AND m.meeting_summary IS NULL"
                        + _VOTE_GATE +
                        " ORDER BY m.meeting_date DESC",
                    )
                meetings = cur.fetchall()
                if args.limit:
                    meetings = meetings[:args.limit]
                logger.info(f"Found {len(meetings)} meetings to summarize")
                for mid, meeting_date, meeting_type in meetings:
                    items = _fetch_items(cur, mid)
                    logger.info(f"  {meeting_date} ({meeting_type}): {len(items)} items")
                    context = _build_meeting_context(items)
                    print(f"\n--- {meeting_date} ({meeting_type}) ---")
                    print(context[:500])
                    print("...")
                logger.info(f"Done. Processed {len(meetings)}/{len(meetings)} meetings.")
        else:
            generate_summaries(
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
