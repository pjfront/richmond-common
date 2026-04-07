"""
Generate meeting-level recaps from agenda items, votes, and public comment themes.

Produces a 4-6 paragraph narrative recap for each meeting, stored in
meetings.meeting_recap. Richer than the terse meeting_summary (bullets for
listings); the recap tells the full story of what happened at a meeting
including vote breakdowns, community voice themes, and continued items.

Requires votes/motions to exist (same vote gate as meeting_summary).

Usage:
    python generate_meeting_recaps.py                  # all ungenerated
    python generate_meeting_recaps.py --limit 10       # first 10
    python generate_meeting_recaps.py --meeting-id X   # specific meeting
    python generate_meeting_recaps.py --force           # regenerate all
    python generate_meeting_recaps.py --dry-run         # preview without saving

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


# ── Agenda items with vote outcomes and comment counts ──────────────

_AGENDA_ITEMS_QUERY = """
    SELECT
        ai.id,
        ai.item_number,
        ai.title,
        ai.summary_headline,
        ai.plain_language_summary,
        ai.category,
        ai.financial_amount,
        ai.is_consent_calendar,
        ai.department,
        ai.topic_label,
        ai.continued_to,
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

# ── Theme narratives per agenda item ────────────────────────────────

_THEME_NARRATIVES_QUERY = """
    SELECT
        itn.agenda_item_id,
        ct.label as theme_label,
        itn.narrative,
        itn.comment_count
    FROM item_theme_narratives itn
    JOIN comment_themes ct ON ct.id = itn.theme_id
    JOIN agenda_items ai ON ai.id = itn.agenda_item_id
    WHERE ai.meeting_id = %s
    AND itn.confidence >= 0.7
    ORDER BY itn.comment_count DESC
"""

# ── Vote gate: same as meeting_summary ──────────────────────────────

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
            "id": str(row[0]),
            "item_number": row[1],
            "title": row[2],
            "summary_headline": row[3],
            "plain_language_summary": row[4],
            "category": row[5],
            "financial_amount": row[6],
            "is_consent_calendar": row[7],
            "department": row[8],
            "topic_label": row[9],
            "continued_to": row[10],
            "vote_result": row[11] or "",
            "vote_detail": row[12] or "",
            "comment_count": row[13] or 0,
            "nay_count": row[14] or 0,
        }
        for row in cur.fetchall()
    ]


def _fetch_theme_narratives(cur, meeting_id: str) -> dict[str, list[dict]]:
    """Fetch comment theme narratives grouped by agenda item ID."""
    cur.execute(_THEME_NARRATIVES_QUERY, (meeting_id,))
    themes_by_item: dict[str, list[dict]] = {}
    for row in cur.fetchall():
        item_id = str(row[0])
        if item_id not in themes_by_item:
            themes_by_item[item_id] = []
        themes_by_item[item_id].append({
            "theme_label": row[1],
            "narrative": row[2],
            "comment_count": row[3],
        })
    return themes_by_item


def _build_recap_context(
    items: list[dict],
    themes_by_item: dict[str, list[dict]],
    meeting_meta: dict,
) -> str:
    """Build structured text block for the LLM.

    Combines vote outcomes, per-official breakdowns, community voice
    themes, and meeting metadata into a comprehensive recap context.
    """
    lines = []

    # Meeting metadata
    presiding = meeting_meta.get("presiding_officer", "")
    call_time = meeting_meta.get("call_to_order_time", "")
    adj_time = meeting_meta.get("adjournment_time", "")
    meta_parts = [f"Date: {meeting_meta.get('meeting_date', '')}"]
    if presiding:
        meta_parts.append(f"Presiding: {presiding}")
    if call_time:
        meta_parts.append(f"Called to order: {call_time}")
    if adj_time:
        meta_parts.append(f"Adjourned: {adj_time}")
    lines.append("MEETING: " + " | ".join(meta_parts))

    # Total public comment count
    total_comments = sum(i.get("comment_count", 0) for i in items)
    if total_comments > 0:
        lines.append(f"Total public comments across all items: {total_comments}")

    # Separate consent vs action items
    consent_items = []
    action_items = []
    continued_items = []

    for item in items:
        if item.get("continued_to"):
            continued_items.append(item)
        elif item.get("is_consent_calendar"):
            consent_items.append(item)
        else:
            action_items.append(item)

    # Consent calendar
    if consent_items:
        consent_result = ""
        has_consent_votes = any(i.get("vote_result") for i in consent_items)
        if has_consent_votes:
            consent_result = " — PASSED as a block"
        lines.append(f"\nCONSENT CALENDAR ({len(consent_items)} items){consent_result}:")
        for item in consent_items[:15]:
            headline = item.get("summary_headline") or item.get("title", "")
            amount = item.get("financial_amount")
            line = f"  - {headline}"
            if amount:
                line += f" ({amount})"
            lines.append(line)
        if len(consent_items) > 15:
            lines.append(f"  - ... and {len(consent_items) - 15} more routine items")

    # Action items sorted by controversy
    if action_items:
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
            summary = item.get("plain_language_summary", "")
            item_id = item.get("id", "")

            # Vote outcome
            if vote_result:
                outcome = vote_result.upper()
            else:
                outcome = "NO VOTE RECORDED"

            line = f"  [{category}] {headline}"
            if amount:
                line += f" ({amount})"
            line += f" — {outcome}"
            lines.append(line)

            # Vote detail (per-official breakdown)
            if vote_detail and vote_result:
                lines.append(f"    Vote detail: {vote_detail}")

            # Plain language summary
            if summary:
                truncated = summary[:200] + "..." if len(summary) > 200 else summary
                lines.append(f"    Summary: {truncated}")

            # Comment count and theme narratives
            if comments > 0:
                lines.append(f"    Public comments: {comments}")
                item_themes = themes_by_item.get(item_id, [])
                for theme in item_themes[:3]:  # Cap at 3 themes per item
                    narrative = theme.get("narrative", "")
                    if narrative:
                        truncated_narrative = narrative[:150] + "..." if len(narrative) > 150 else narrative
                        lines.append(
                            f'    THEME "{theme["theme_label"]}" '
                            f'({theme["comment_count"]} comments): {truncated_narrative}'
                        )

            if nays > 0:
                lines.append(f"    Split vote: {nays} nay vote(s)")

    # Continued items
    if continued_items:
        lines.append("\nCONTINUED TO FUTURE MEETING:")
        for item in continued_items:
            headline = item.get("summary_headline") or item.get("title", "")
            lines.append(f"  - {headline}")

    return "\n".join(lines)


def _parse_recap(text: str) -> str | None:
    """Parse JSON response to extract meeting_recap."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1:]
        if text.endswith("```"):
            text = text[:-3].strip()

    try:
        data = json.loads(text)
        return (data.get("meeting_recap") or "").strip() or None
    except (json.JSONDecodeError, AttributeError):
        # Try regex extraction from partial JSON
        if '"meeting_recap"' in text:
            try:
                import re
                match = re.search(r'"meeting_recap"\s*:\s*"(.*)"', text, re.DOTALL)
                if match:
                    raw_val = match.group(1)
                    return raw_val.replace("\\n", "\n").strip() or None
            except Exception:
                pass
        logger.warning("Failed to parse JSON, using raw text")
        return text.strip() or None


def generate_recap(
    items: list[dict],
    themes_by_item: dict[str, list[dict]],
    meeting_meta: dict,
) -> dict[str, str | None]:
    """Generate a meeting recap from agenda items, votes, and themes.

    Returns dict with 'meeting_recap' and 'model' keys.
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic package required for recap generation")

    system_prompt = _load_prompt("meeting_recap_system.txt")
    context = _build_recap_context(items, themes_by_item, meeting_meta)

    if not context.strip():
        return {"meeting_recap": None, "model": None}

    user_prompt = f"Write a post-meeting recap for this city council meeting:\n\n{context}"

    client = anthropic.Anthropic(timeout=60.0)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1200,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    recap = _parse_recap(response.content[0].text)
    return {"meeting_recap": recap, "model": response.model}


def generate_recaps(
    conn,
    city_fips: str = "0660620",
    force: bool = False,
    meeting_id: str | None = None,
    limit: int | None = None,
    delay: float = 0.5,
) -> dict:
    """Generate meeting recaps. Callable from data_sync or CLI.

    Returns dict with 'total', 'generated', 'skipped', 'errors' counts.
    """
    stats = {"total": 0, "generated": 0, "skipped": 0, "errors": 0}

    with conn.cursor() as cur:
        # Build meeting query with vote gate
        if meeting_id:
            cur.execute(
                "SELECT m.id, m.meeting_date, m.meeting_type, "
                "m.presiding_officer, m.call_to_order_time, m.adjournment_time "
                "FROM meetings m "
                "WHERE m.id = %s" + _VOTE_GATE,
                (meeting_id,),
            )
        elif force:
            cur.execute(
                "SELECT m.id, m.meeting_date, m.meeting_type, "
                "m.presiding_officer, m.call_to_order_time, m.adjournment_time "
                "FROM meetings m "
                "WHERE m.city_fips = %s" + _VOTE_GATE +
                " ORDER BY m.meeting_date DESC",
                (city_fips,),
            )
        else:
            cur.execute(
                "SELECT m.id, m.meeting_date, m.meeting_type, "
                "m.presiding_officer, m.call_to_order_time, m.adjournment_time "
                "FROM meetings m "
                "WHERE m.city_fips = %s AND m.meeting_recap IS NULL"
                + _VOTE_GATE +
                " ORDER BY m.meeting_date DESC",
                (city_fips,),
            )

        meetings = cur.fetchall()
        if limit:
            meetings = meetings[:limit]

        stats["total"] = len(meetings)
        logger.info(f"Found {len(meetings)} meetings to generate recaps for")

        for mid, meeting_date, meeting_type, presiding, call_time, adj_time in meetings:
            items = _fetch_items(cur, mid)

            if not items:
                logger.info(f"  {meeting_date} ({meeting_type}): no non-procedural items, skipping")
                stats["skipped"] += 1
                continue

            # Fetch theme narratives for this meeting's items
            themes_by_item = _fetch_theme_narratives(cur, mid)

            meeting_meta = {
                "meeting_date": str(meeting_date),
                "meeting_type": meeting_type,
                "presiding_officer": presiding or "",
                "call_to_order_time": call_time or "",
                "adjournment_time": adj_time or "",
            }

            theme_count = sum(len(v) for v in themes_by_item.values())
            logger.info(
                f"  {meeting_date} ({meeting_type}): {len(items)} items, "
                f"{theme_count} theme narratives"
            )

            try:
                result = generate_recap(items, themes_by_item, meeting_meta)
                if result["meeting_recap"]:
                    cur.execute(
                        "UPDATE meetings SET meeting_recap = %s WHERE id = %s",
                        (result["meeting_recap"], mid),
                    )
                    conn.commit()
                    logger.info(f"    Saved recap ({len(result['meeting_recap'])} chars)")
                    stats["generated"] += 1
                else:
                    logger.warning(f"    No recap generated")
                    stats["skipped"] += 1
            except Exception as e:
                logger.error(f"    Error: {e}")
                conn.rollback()
                stats["errors"] += 1

            if delay > 0:
                time.sleep(delay)

    logger.info(f"Done. Generated {stats['generated']}/{stats['total']} recaps.")
    return stats


def main():
    parser = argparse.ArgumentParser(description="Generate meeting-level recaps")
    parser.add_argument("--limit", type=int, help="Max meetings to process")
    parser.add_argument("--meeting-id", help="Process specific meeting")
    parser.add_argument("--force", action="store_true", help="Regenerate existing recaps")
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
                        "SELECT m.id, m.meeting_date, m.meeting_type, "
                        "m.presiding_officer, m.call_to_order_time, m.adjournment_time "
                        "FROM meetings m "
                        "WHERE m.id = %s" + _VOTE_GATE,
                        (args.meeting_id,),
                    )
                else:
                    cur.execute(
                        "SELECT m.id, m.meeting_date, m.meeting_type, "
                        "m.presiding_officer, m.call_to_order_time, m.adjournment_time "
                        "FROM meetings m "
                        "WHERE m.city_fips = '0660620' AND m.meeting_recap IS NULL"
                        + _VOTE_GATE +
                        " ORDER BY m.meeting_date DESC",
                    )
                meetings = cur.fetchall()
                if args.limit:
                    meetings = meetings[:args.limit]
                logger.info(f"Found {len(meetings)} meetings to generate recaps for")
                for mid, meeting_date, meeting_type, presiding, call_time, adj_time in meetings:
                    items = _fetch_items(cur, mid)
                    themes_by_item = _fetch_theme_narratives(cur, mid)
                    meeting_meta = {
                        "meeting_date": str(meeting_date),
                        "meeting_type": meeting_type,
                        "presiding_officer": presiding or "",
                        "call_to_order_time": call_time or "",
                        "adjournment_time": adj_time or "",
                    }
                    context = _build_recap_context(items, themes_by_item, meeting_meta)
                    theme_count = sum(len(v) for v in themes_by_item.values())
                    print(f"\n--- {meeting_date} ({meeting_type}) ---")
                    print(f"  {len(items)} items, {theme_count} theme narratives")
                    print(context[:1000])
                    if len(context) > 1000:
                        print("...")
        else:
            generate_recaps(
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
