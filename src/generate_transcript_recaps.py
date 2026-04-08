"""
Generate meeting recaps from transcript text (YouTube/Granicus captions).

Unlike generate_meeting_recaps.py which requires votes/motions from official
minutes, this works from the raw meeting transcript + agenda item titles.
Available immediately after a meeting (YouTube auto-captions) or days later
(Granicus professional transcripts).

Usage:
    python generate_transcript_recaps.py                          # all ungenerated
    python generate_transcript_recaps.py --meeting-date 2026-04-07
    python generate_transcript_recaps.py --source youtube         # force source
    python generate_transcript_recaps.py --force                  # regenerate all
    python generate_transcript_recaps.py --dry-run                # preview
    python generate_transcript_recaps.py --compare 2026-03-03     # compare sources

Publication tier: Graduated (AI-generated content, operator review before public).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# Maximum chars of transcript to send (avoid exceeding context window)
MAX_TRANSCRIPT_CHARS = 400_000  # ~100K tokens


def _load_prompt(filename: str) -> str:
    path = _PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text().strip()


# ── Agenda items (titles only, no votes needed) ──────────────

_AGENDA_ITEMS_QUERY = """
    SELECT
        ai.item_number,
        ai.title,
        ai.summary_headline,
        ai.category,
        ai.financial_amount,
        ai.is_consent_calendar
    FROM agenda_items ai
    WHERE ai.meeting_id = %s
    AND ai.category != 'procedural'
    ORDER BY ai.item_number
"""


def _fetch_agenda_titles(cur, meeting_id: str) -> list[dict]:
    """Fetch agenda item titles for a single meeting (no votes needed)."""
    cur.execute(_AGENDA_ITEMS_QUERY, (meeting_id,))
    return [
        {
            "item_number": row[0],
            "title": row[1],
            "summary_headline": row[2],
            "category": row[3],
            "financial_amount": row[4],
            "is_consent_calendar": row[5],
        }
        for row in cur.fetchall()
    ]


# ── Context builder ──────────────────────────────────────────

def _build_transcript_context(
    transcript_text: str,
    agenda_items: list[dict],
    meeting_meta: dict,
) -> str:
    """Build context block combining transcript + agenda for the LLM."""
    lines = []

    # Meeting metadata
    meta_parts = [f"Date: {meeting_meta.get('meeting_date', '')}"]
    meeting_type = meeting_meta.get("meeting_type", "")
    if meeting_type:
        meta_parts.append(f"Type: {meeting_type}")
    lines.append("MEETING: " + " | ".join(meta_parts))

    # Agenda items (titles only — gives the LLM structure to map against)
    if agenda_items:
        consent = [i for i in agenda_items if i.get("is_consent_calendar")]
        action = [i for i in agenda_items if not i.get("is_consent_calendar")]

        if consent:
            lines.append(f"\nCONSENT CALENDAR ({len(consent)} items):")
            for item in consent[:10]:
                headline = item.get("summary_headline") or item.get("title", "")
                amount = item.get("financial_amount")
                line = f"  - [{item.get('item_number', '')}] {headline}"
                if amount:
                    line += f" ({amount})"
                lines.append(line)
            if len(consent) > 10:
                lines.append(f"  - ... and {len(consent) - 10} more")

        if action:
            lines.append(f"\nACTION/DISCUSSION ITEMS ({len(action)} items):")
            for item in action:
                headline = item.get("summary_headline") or item.get("title", "")
                category = item.get("category", "")
                amount = item.get("financial_amount")
                line = f"  - [{item.get('item_number', '')}] [{category}] {headline}"
                if amount:
                    line += f" ({amount})"
                lines.append(line)

    # Transcript (truncated if needed)
    transcript = transcript_text
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        transcript = transcript[:MAX_TRANSCRIPT_CHARS]
        lines.append(
            f"\nTRANSCRIPT (truncated to {MAX_TRANSCRIPT_CHARS:,} chars "
            f"of {len(transcript_text):,} total):"
        )
    else:
        lines.append(f"\nTRANSCRIPT ({len(transcript):,} chars):")
    lines.append(transcript)

    return "\n".join(lines)


# ── JSON parsing ─────────────────────────────────────────────

def _parse_recap(text: str) -> str | None:
    """Parse JSON response to extract transcript_recap."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1:]
        if text.endswith("```"):
            text = text[:-3].strip()

    try:
        data = json.loads(text)
        return (data.get("transcript_recap") or "").strip() or None
    except (json.JSONDecodeError, AttributeError):
        import re
        if '"transcript_recap"' in text:
            try:
                match = re.search(r'"transcript_recap"\s*:\s*"(.*)"', text, re.DOTALL)
                if match:
                    raw_val = match.group(1)
                    return raw_val.replace("\\n", "\n").strip() or None
            except Exception:
                pass
        logger.warning("Failed to parse JSON, using raw text")
        return text.strip() or None


# ── Single recap generation ──────────────────────────────────

def generate_transcript_recap(
    transcript_text: str,
    agenda_items: list[dict],
    meeting_meta: dict,
    source: str = "youtube",
) -> dict[str, str | None]:
    """Generate a meeting recap from transcript text.

    Returns dict with 'transcript_recap', 'model', and 'source' keys.
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic package required for recap generation")

    system_prompt = _load_prompt("transcript_recap_system.txt")
    context = _build_transcript_context(transcript_text, agenda_items, meeting_meta)

    if not context.strip():
        return {"transcript_recap": None, "model": None, "source": source}

    user_prompt = (
        f"Write a post-meeting recap for this city council meeting "
        f"based on the transcript below:\n\n{context}"
    )

    client = anthropic.Anthropic(timeout=120.0)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    recap = _parse_recap(response.content[0].text)
    return {"transcript_recap": recap, "model": response.model, "source": source}


# ── Batch generation ─────────────────────────────────────────

def generate_transcript_recaps(
    conn,
    city_fips: str = "0660620",
    force: bool = False,
    meeting_date: str | None = None,
    source: str | None = None,
    limit: int | None = None,
    delay: float = 0.5,
) -> dict:
    """Generate transcript recaps for meetings with local transcripts.

    Returns dict with 'total', 'generated', 'skipped', 'errors' counts.
    """
    from transcript_utils import fetch_best_transcript, get_transcript_for_source

    stats = {"total": 0, "generated": 0, "skipped": 0, "errors": 0}

    with conn.cursor() as cur:
        if meeting_date:
            cur.execute(
                "SELECT m.id, m.meeting_date, m.meeting_type "
                "FROM meetings m "
                "WHERE m.city_fips = %s AND m.meeting_date = %s",
                (city_fips, meeting_date),
            )
        elif force:
            cur.execute(
                "SELECT m.id, m.meeting_date, m.meeting_type "
                "FROM meetings m "
                "WHERE m.city_fips = %s "
                "ORDER BY m.meeting_date DESC",
                (city_fips,),
            )
        else:
            cur.execute(
                "SELECT m.id, m.meeting_date, m.meeting_type "
                "FROM meetings m "
                "WHERE m.city_fips = %s AND m.transcript_recap IS NULL "
                "ORDER BY m.meeting_date DESC",
                (city_fips,),
            )

        meetings = cur.fetchall()
        if limit:
            meetings = meetings[:limit]

        # Filter to meetings with local transcripts
        meetings_with_transcripts = []
        for mid, mdate, mtype in meetings:
            date_str = str(mdate)
            if source:
                text = get_transcript_for_source(date_str, source)
                if text:
                    meetings_with_transcripts.append(
                        (mid, date_str, mtype, text, source)
                    )
            else:
                result = fetch_best_transcript(date_str)
                if result:
                    text, src = result
                    meetings_with_transcripts.append(
                        (mid, date_str, mtype, text, src)
                    )

        stats["total"] = len(meetings_with_transcripts)
        logger.info(
            f"Found {len(meetings_with_transcripts)} meetings with transcripts"
        )

        for mid, mdate, mtype, transcript_text, src in meetings_with_transcripts:
            items = _fetch_agenda_titles(cur, mid)

            if not items:
                logger.info(f"  {mdate}: no agenda items, skipping")
                stats["skipped"] += 1
                continue

            meeting_meta = {
                "meeting_date": mdate,
                "meeting_type": mtype,
            }

            logger.info(
                f"  {mdate} ({mtype}): {len(items)} items, "
                f"source={src}, {len(transcript_text):,} chars"
            )

            try:
                result = generate_transcript_recap(
                    transcript_text, items, meeting_meta, source=src,
                )
                if result["transcript_recap"]:
                    cur.execute(
                        "UPDATE meetings SET "
                        "transcript_recap = %s, "
                        "transcript_recap_source = %s, "
                        "transcript_recap_generated_at = %s "
                        "WHERE id = %s",
                        (
                            result["transcript_recap"],
                            src,
                            datetime.now(timezone.utc),
                            mid,
                        ),
                    )
                    conn.commit()
                    logger.info(
                        f"    Saved recap ({len(result['transcript_recap'])} chars)"
                    )
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


# ── Compare mode ─────────────────────────────────────────────

def compare_sources(
    conn,
    meeting_date: str,
    city_fips: str = "0660620",
) -> dict[str, str | None]:
    """Generate recaps from both YouTube and Granicus for comparison.

    Returns dict with 'youtube_recap' and 'granicus_recap'.
    """
    from transcript_utils import get_transcript_for_source

    with conn.cursor() as cur:
        cur.execute(
            "SELECT m.id, m.meeting_date, m.meeting_type "
            "FROM meetings m "
            "WHERE m.city_fips = %s AND m.meeting_date = %s",
            (city_fips, meeting_date),
        )
        row = cur.fetchone()
        if not row:
            logger.error(f"No meeting found for {meeting_date}")
            return {"youtube_recap": None, "granicus_recap": None}

        mid, mdate, mtype = row
        items = _fetch_agenda_titles(cur, mid)
        meeting_meta = {"meeting_date": str(mdate), "meeting_type": mtype}

    results = {}
    for src in ["youtube", "granicus"]:
        text = get_transcript_for_source(meeting_date, src)
        if not text:
            logger.info(f"  No {src} transcript for {meeting_date}")
            results[f"{src}_recap"] = None
            continue

        logger.info(f"  Generating {src} recap ({len(text):,} chars)...")
        result = generate_transcript_recap(text, items, meeting_meta, source=src)
        results[f"{src}_recap"] = result.get("transcript_recap")

    return results


# ── CLI ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate meeting recaps from transcripts"
    )
    parser.add_argument("--limit", type=int, help="Max meetings to process")
    parser.add_argument("--meeting-date", help="Process specific meeting date")
    parser.add_argument(
        "--source", choices=["youtube", "granicus"],
        help="Force specific transcript source",
    )
    parser.add_argument(
        "--force", action="store_true", help="Regenerate existing recaps"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without saving"
    )
    parser.add_argument(
        "--compare", metavar="DATE",
        help="Compare YouTube vs Granicus for a meeting date",
    )
    parser.add_argument(
        "--delay", type=float, default=0.5,
        help="Delay between API calls (seconds)",
    )
    args = parser.parse_args()

    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])

    try:
        if args.compare:
            results = compare_sources(conn, args.compare)
            for src in ["youtube", "granicus"]:
                recap = results.get(f"{src}_recap")
                print(f"\n{'='*60}")
                print(f"  {src.upper()} RECAP")
                print(f"{'='*60}")
                if recap:
                    print(recap)
                else:
                    print("  (no transcript available)")
            return

        if args.dry_run:
            from transcript_utils import (
                fetch_best_transcript,
                get_transcript_for_source,
            )

            with conn.cursor() as cur:
                if args.meeting_date:
                    cur.execute(
                        "SELECT m.id, m.meeting_date, m.meeting_type "
                        "FROM meetings m "
                        "WHERE m.city_fips = '0660620' AND m.meeting_date = %s",
                        (args.meeting_date,),
                    )
                else:
                    cur.execute(
                        "SELECT m.id, m.meeting_date, m.meeting_type "
                        "FROM meetings m "
                        "WHERE m.city_fips = '0660620' "
                        "AND m.transcript_recap IS NULL "
                        "ORDER BY m.meeting_date DESC",
                    )
                meetings = cur.fetchall()
                if args.limit:
                    meetings = meetings[:args.limit]

                for mid, mdate, mtype in meetings:
                    date_str = str(mdate)
                    if args.source:
                        text = get_transcript_for_source(date_str, args.source)
                        src = args.source
                    else:
                        result = fetch_best_transcript(date_str)
                        if not result:
                            continue
                        text, src = result

                    if not text:
                        continue

                    items = _fetch_agenda_titles(cur, mid)
                    meeting_meta = {
                        "meeting_date": date_str,
                        "meeting_type": mtype,
                    }
                    context = _build_transcript_context(
                        text, items, meeting_meta,
                    )
                    print(f"\n--- {mdate} ({mtype}, {src}) ---")
                    print(f"  {len(items)} agenda items")
                    print(f"  transcript: {len(text):,} chars")
                    print(f"  context: {len(context):,} chars")
                    # Show first 500 chars of context
                    print(context[:500])
                    if len(context) > 500:
                        print("...")
        else:
            generate_transcript_recaps(
                conn,
                force=args.force,
                meeting_date=args.meeting_date,
                source=args.source,
                limit=args.limit,
                delay=args.delay,
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
