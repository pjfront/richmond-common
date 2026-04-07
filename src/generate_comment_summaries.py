"""
Generate per-agenda-item comment summaries from public comment data.

Produces a 2-3 sentence narrative synthesis for agenda items that received
public testimony, stored in agenda_items.comment_summary. Uses existing
item_theme_narratives when available (cheaper, richer context), falls back
to raw speaker names and methods from public_comments.

Requires migration 081 (comment_summary column).

Usage:
    python generate_comment_summaries.py                  # all ungenerated
    python generate_comment_summaries.py --limit 10       # first 10
    python generate_comment_summaries.py --meeting-id X   # specific meeting
    python generate_comment_summaries.py --force           # regenerate all
    python generate_comment_summaries.py --dry-run         # preview without saving

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


# ── Queries ──────────────────────────────────────────────────

_ITEMS_QUERY = """
    SELECT ai.id, ai.title, ai.summary_headline, ai.topic_label,
           ai.public_comment_count, m.meeting_date
    FROM agenda_items ai
    JOIN meetings m ON m.id = ai.meeting_id
    WHERE ai.public_comment_count > 0
      AND m.city_fips = %s
      {filter}
    ORDER BY m.meeting_date DESC, ai.item_number
"""

_THEME_NARRATIVES_QUERY = """
    SELECT ct.label, itn.narrative, itn.comment_count
    FROM item_theme_narratives itn
    JOIN comment_themes ct ON ct.id = itn.theme_id
    WHERE itn.agenda_item_id = %s
      AND itn.confidence >= 0.7
    ORDER BY itn.comment_count DESC
"""

_COMMENTS_QUERY = """
    SELECT speaker_name, method, comment_type
    FROM public_comments
    WHERE agenda_item_id = %s
    ORDER BY created_at
"""


def _build_context(
    item: dict,
    theme_narratives: list[dict],
    raw_comments: list[dict],
) -> str:
    """Build context for the LLM from available data."""
    lines = [
        f"Agenda item: {item['title']}",
        f"Date: {item['meeting_date']}",
        f"Total speakers: {item['public_comment_count']}",
    ]

    if item.get("summary_headline"):
        lines.append(f"Summary: {item['summary_headline']}")

    # Prefer theme narratives (pre-analyzed, richer)
    if theme_narratives:
        lines.append("\nThemes from public testimony:")
        for tn in theme_narratives[:5]:
            lines.append(
                f'  - "{tn["label"]}" ({tn["comment_count"]} speakers): {tn["narrative"]}'
            )
    elif raw_comments:
        # Fall back to raw comment metadata
        methods = {}
        for c in raw_comments:
            m = c.get("method", "unknown")
            methods[m] = methods.get(m, 0) + 1
        method_str = ", ".join(f"{count} {method}" for method, count in methods.items())
        lines.append(f"\nComment methods: {method_str}")
        # List first few speaker names for context
        names = [c["speaker_name"] for c in raw_comments[:10] if c.get("speaker_name")]
        if names:
            lines.append(f"Speakers include: {', '.join(names)}")

    return "\n".join(lines)


def _parse_summary(text: str) -> str | None:
    """Parse JSON response to extract comment_summary."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1:]
        if text.endswith("```"):
            text = text[:-3].strip()

    try:
        data = json.loads(text)
        return (data.get("comment_summary") or "").strip() or None
    except (json.JSONDecodeError, AttributeError):
        logger.warning("Failed to parse JSON, using raw text")
        return text.strip() or None


def generate_summary(item: dict, theme_narratives: list[dict], raw_comments: list[dict]) -> dict:
    """Generate a comment summary for a single agenda item."""
    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic package required for comment summary generation")

    system_prompt = _load_prompt("comment_summary_system.txt")
    context = _build_context(item, theme_narratives, raw_comments)

    client = anthropic.Anthropic(timeout=30.0)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        system=system_prompt,
        messages=[{"role": "user", "content": f"Summarize the public testimony on this agenda item:\n\n{context}"}],
    )

    summary = _parse_summary(response.content[0].text)
    return {"comment_summary": summary, "model": response.model}


def generate_comment_summaries(
    conn,
    city_fips: str = "0660620",
    force: bool = False,
    meeting_id: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    delay: float = 0.3,
) -> dict:
    """Generate comment summaries. Callable from data_sync or CLI.

    Returns dict with 'total', 'generated', 'skipped', 'errors' counts.
    """
    stats = {"total": 0, "generated": 0, "skipped": 0, "errors": 0}

    with conn.cursor() as cur:
        # Build filter
        if meeting_id:
            filter_clause = f"AND ai.meeting_id = '{meeting_id}'"
        elif force:
            filter_clause = ""
        else:
            filter_clause = "AND ai.comment_summary IS NULL"

        query = _ITEMS_QUERY.format(filter=filter_clause)
        cur.execute(query, (city_fips,))

        items = [
            {
                "id": str(row[0]),
                "title": row[1],
                "summary_headline": row[2],
                "topic_label": row[3],
                "public_comment_count": row[4],
                "meeting_date": str(row[5]),
            }
            for row in cur.fetchall()
        ]

        if limit:
            items = items[:limit]

        stats["total"] = len(items)
        logger.info(f"Found {len(items)} agenda items with public comments to summarize")

        for item in items:
            # Fetch theme narratives
            cur.execute(_THEME_NARRATIVES_QUERY, (item["id"],))
            theme_narratives = [
                {"label": row[0], "narrative": row[1], "comment_count": row[2]}
                for row in cur.fetchall()
            ]

            # Fetch raw comments as fallback
            cur.execute(_COMMENTS_QUERY, (item["id"],))
            raw_comments = [
                {"speaker_name": row[0], "method": row[1], "comment_type": row[2]}
                for row in cur.fetchall()
            ]

            # Skip if no useful data (no themes and no named speakers)
            if not theme_narratives and not raw_comments:
                logger.info(f"  {item['meeting_date']} — {item['title'][:60]}: no comment data, skipping")
                stats["skipped"] += 1
                continue

            try:
                result = generate_summary(item, theme_narratives, raw_comments)
                summary = result.get("comment_summary")

                if not summary:
                    logger.warning(f"  {item['meeting_date']} — empty summary returned")
                    stats["skipped"] += 1
                    continue

                logger.info(
                    f"  {item['meeting_date']} — {item['title'][:50]}: "
                    f"{len(summary)} chars (model: {result.get('model', 'unknown')})"
                )

                if dry_run:
                    logger.info(f"    [DRY RUN] {summary}")
                else:
                    cur.execute(
                        "UPDATE agenda_items SET comment_summary = %s WHERE id = %s",
                        (summary, item["id"]),
                    )
                    conn.commit()

                stats["generated"] += 1

            except Exception as e:
                logger.error(f"  {item['meeting_date']} — {item['title'][:50]}: {e}")
                stats["errors"] += 1

            if delay > 0:
                time.sleep(delay)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate AI comment summaries for agenda items with public testimony.",
    )
    parser.add_argument("--city-fips", default="0660620", help="City FIPS code")
    parser.add_argument("--meeting-id", help="Generate for specific meeting only")
    parser.add_argument("--limit", type=int, help="Max items to process")
    parser.add_argument("--force", action="store_true", help="Regenerate existing summaries")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--delay", type=float, default=0.3, help="Delay between API calls")
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        sys.exit(1)

    import psycopg2

    conn = psycopg2.connect(database_url)

    try:
        stats = generate_comment_summaries(
            conn,
            city_fips=args.city_fips,
            force=args.force,
            meeting_id=args.meeting_id,
            limit=args.limit,
            dry_run=args.dry_run,
            delay=args.delay,
        )

        prefix = "[DRY RUN] " if args.dry_run else ""
        logger.info(
            f"\n{prefix}Done: {stats['generated']} generated, "
            f"{stats['skipped']} skipped, {stats['errors']} errors "
            f"(out of {stats['total']} items)"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
