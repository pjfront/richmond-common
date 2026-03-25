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
    """Build a structured text block from agenda items for the LLM."""
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
        lines.append(f"\nACTION ITEMS ({len(action_items)} items):")
        for item in action_items:
            headline = item.get("summary_headline") or item.get("title", "")
            category = item.get("category", "")
            amount = item.get("financial_amount")
            vote_result = item.get("vote_result", "")
            vote_detail = item.get("vote_detail", "")

            line = f"  - [{category}] {headline}"
            if amount:
                line += f" ({amount})"
            if vote_result:
                line += f" — {vote_result}"
            if vote_detail:
                line += f" {vote_detail}"
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
        with conn.cursor() as cur:
            # Find meetings needing summaries
            if args.meeting_id:
                cur.execute(
                    "SELECT id, meeting_date, meeting_type FROM meetings WHERE id = %s",
                    (args.meeting_id,),
                )
            elif args.force:
                cur.execute(
                    "SELECT id, meeting_date, meeting_type FROM meetings "
                    "WHERE city_fips = '0660620' ORDER BY meeting_date DESC"
                )
            else:
                cur.execute(
                    "SELECT id, meeting_date, meeting_type FROM meetings "
                    "WHERE city_fips = '0660620' AND meeting_summary IS NULL "
                    "ORDER BY meeting_date DESC"
                )

            meetings = cur.fetchall()
            if args.limit:
                meetings = meetings[: args.limit]

            logger.info(f"Found {len(meetings)} meetings to summarize")

            processed = 0
            for meeting_id, meeting_date, meeting_type in meetings:
                # Fetch agenda items with their summaries and vote outcomes
                cur.execute("""
                    SELECT
                        ai.title,
                        ai.summary_headline,
                        ai.category,
                        ai.financial_amount,
                        ai.is_consent_calendar,
                        CASE
                            WHEN EXISTS (
                                SELECT 1 FROM motions m
                                WHERE m.agenda_item_id = ai.id AND m.result = 'Passed'
                            ) THEN 'Passed'
                            WHEN EXISTS (
                                SELECT 1 FROM motions m
                                WHERE m.agenda_item_id = ai.id AND m.result = 'Failed'
                            ) THEN 'Failed'
                            ELSE ''
                        END as vote_result,
                        (
                            SELECT string_agg(
                                v.council_member || ': ' || v.vote, ', '
                                ORDER BY v.council_member
                            )
                            FROM motions m
                            JOIN votes v ON v.motion_id = m.id
                            WHERE m.agenda_item_id = ai.id
                            AND m.result IS NOT NULL
                            LIMIT 1
                        ) as vote_detail
                    FROM agenda_items ai
                    WHERE ai.meeting_id = %s
                    AND ai.category != 'procedural'
                    ORDER BY ai.item_number
                """, (meeting_id,))

                items = []
                for row in cur.fetchall():
                    items.append({
                        "title": row[0],
                        "summary_headline": row[1],
                        "category": row[2],
                        "financial_amount": row[3],
                        "is_consent_calendar": row[4],
                        "vote_result": row[5] or "",
                        "vote_detail": row[6] or "",
                    })

                if not items:
                    logger.info(f"  {meeting_date} ({meeting_type}): no non-procedural items, skipping")
                    continue

                logger.info(f"  {meeting_date} ({meeting_type}): {len(items)} items")

                if args.dry_run:
                    context = _build_meeting_context(items)
                    print(f"\n--- {meeting_date} ({meeting_type}) ---")
                    print(context[:500])
                    print("...")
                    processed += 1
                    continue

                try:
                    result = generate_meeting_summary(items)
                    if result["meeting_summary"]:
                        cur.execute(
                            "UPDATE meetings SET meeting_summary = %s WHERE id = %s",
                            (result["meeting_summary"], meeting_id),
                        )
                        conn.commit()
                        logger.info(f"    Saved summary ({len(result['meeting_summary'])} chars)")
                        processed += 1
                    else:
                        logger.warning(f"    No summary generated")
                except Exception as e:
                    logger.error(f"    Error: {e}")
                    conn.rollback()

                if args.delay > 0:
                    time.sleep(args.delay)

        logger.info(f"Done. Processed {processed}/{len(meetings)} meetings.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
