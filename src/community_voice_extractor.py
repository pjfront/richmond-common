"""
S21: Community Voice — enhanced transcript extraction.

Extracts individual public comment speakers with names, methods, and
summaries from KCRT TV YouTube transcripts. Fills the `public_comments`
table with rich per-speaker data (S20 only wrote integer counts).

Workflow:
  1. Find meetings with transcripts but no transcript-sourced comments
  2. Send transcript + agenda items to Claude API
  3. Write individual `public_comments` rows with source='youtube_transcript'

Usage:
  python community_voice_extractor.py extract                   # All meetings
  python community_voice_extractor.py extract --meeting-date 2026-03-03
  python community_voice_extractor.py extract --dry-run
  python community_voice_extractor.py extract --limit 3
  python community_voice_extractor.py status                    # Show coverage
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load .env from repo root
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

from db import get_connection, RICHMOND_FIPS  # noqa: E402

# -- Constants ------------------------------------------------

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 8000  # Individual speaker data is much larger than counts

TRANSCRIPT_DIR = Path(__file__).parent.parent / "data" / "transcripts"
PROMPT_PATH = Path(__file__).parent / "prompts" / "community_voice_system.txt"
RESULTS_DIR = TRANSCRIPT_DIR / "community_voice"

SOURCE_YOUTUBE = "youtube_transcript"
SOURCE_GRANICUS = "granicus_transcript"


def _ensure_dirs() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# -- DB helpers -----------------------------------------------


def _get_agenda_items_text(meeting_id: str) -> str:
    """Get formatted agenda items list for a meeting."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """SELECT item_number, LEFT(title, 120) as title
               FROM agenda_items
               WHERE meeting_id = %s
               ORDER BY item_number""",
            (meeting_id,),
        )
        rows = cur.fetchall()
    conn.close()
    return "\n".join(f"{r[0]} - {r[1]}" for r in rows)


def _get_agenda_item_ids(meeting_id: str) -> dict[str, str]:
    """Get mapping of item_number -> agenda_item UUID for a meeting."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT item_number, id FROM agenda_items WHERE meeting_id = %s",
            (meeting_id,),
        )
        rows = cur.fetchall()
    conn.close()
    return {r[0]: str(r[1]) for r in rows}


def _normalize_item_number(s: str) -> str:
    """Normalize item numbers for fuzzy matching.

    'P5' -> 'p.5', 'N3D' -> 'n.3.d', 'V6a' -> 'v.6.a'
    """
    s = s.strip().upper()
    result = re.sub(r"([A-Z])(\d)", r"\1.\2", s)
    result = re.sub(r"(\d)([A-Z])", r"\1.\2", result)
    return result.lower()


def _resolve_item_id(
    item_number: str,
    item_id_map: dict[str, str],
) -> str | None:
    """Resolve an item number to a UUID, with fuzzy matching."""
    # Exact match
    if item_number in item_id_map:
        return item_id_map[item_number]

    # Normalized match
    norm = _normalize_item_number(item_number)
    for db_num, db_id in item_id_map.items():
        if _normalize_item_number(db_num) == norm:
            return db_id

    return None


def _meetings_needing_extraction(
    city_fips: str = RICHMOND_FIPS,
    meeting_date: str | None = None,
    include_already_extracted: bool = False,
) -> list[dict[str, Any]]:
    """Find meetings with transcripts that need community voice extraction.

    Returns meetings that have local transcripts but no transcript-sourced
    public_comments rows (unless include_already_extracted=True).
    """
    if not TRANSCRIPT_DIR.exists():
        return []

    conn = get_connection()
    meetings: list[dict[str, Any]] = []

    for path in sorted(TRANSCRIPT_DIR.glob("*_clean.txt")):
        name = path.stem.replace("_clean", "")
        if not re.match(r"\d{4}-\d{2}-\d{2}", name):
            continue

        if meeting_date and name != meeting_date:
            continue

        with conn.cursor() as cur:
            cur.execute(
                """SELECT m.id,
                          (SELECT COUNT(*) FROM agenda_items ai WHERE ai.meeting_id = m.id) as item_count
                   FROM meetings m
                   WHERE m.city_fips = %s AND m.meeting_date = %s AND m.meeting_type = 'regular'
                   LIMIT 1""",
                (city_fips, name),
            )
            row = cur.fetchone()
            if not row:
                continue

            meeting_id = str(row[0])
            item_count = row[1]

            # Check if already has transcript-sourced comments
            if not include_already_extracted:
                cur.execute(
                    """SELECT COUNT(*) FROM public_comments
                       WHERE meeting_id = %s AND source = %s""",
                    (meeting_id, SOURCE_YOUTUBE),
                )
                existing = cur.fetchone()[0]
                if existing > 0:
                    continue

            meetings.append({
                "meeting_date": name,
                "meeting_id": meeting_id,
                "item_count": item_count,
                "transcript_path": path,
            })

    conn.close()
    return meetings


# -- Extraction -----------------------------------------------


def _load_system_prompt() -> str:
    """Load the community voice extraction prompt."""
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def extract_speakers(
    transcript_path: Path,
    meeting_id: str,
    meeting_date: str,
) -> dict[str, Any] | None:
    """Send transcript to Claude API and extract individual speakers.

    Returns parsed JSON with speakers list, or None on failure.
    """
    if anthropic is None:
        print("ERROR: anthropic package required. Run: pip install anthropic")
        return None

    transcript = transcript_path.read_text(encoding="utf-8")
    agenda_text = _get_agenda_items_text(meeting_id)
    system_prompt = _load_system_prompt()

    user_prompt = f"""AGENDA ITEMS FOR THIS MEETING ({meeting_date}):
{agenda_text}

TRANSCRIPT:
{transcript}

Extract every individual public comment speaker with their name, method, agenda item, and a 1-3 sentence summary of what they said. Return JSON."""

    est_tokens = len(transcript) // 4
    print(f"  Sending to Claude API (~{est_tokens:,} input tokens)...")

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    text = response.content[0].text
    cost = (
        response.usage.input_tokens * 0.003 / 1000
        + response.usage.output_tokens * 0.015 / 1000
    )

    print(
        f"  API response: {response.usage.input_tokens:,} in / "
        f"{response.usage.output_tokens:,} out (${cost:.3f})"
    )

    # Parse JSON — strip markdown fences if present
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  ERROR: Failed to parse JSON: {e}")
        print(f"  Raw response: {text[:500]}")
        return None

    speakers = result.get("speakers", [])
    print(f"  Extracted {len(speakers)} speaker entries")

    return result


def import_speakers(
    result: dict[str, Any],
    meeting_id: str,
    meeting_date: str,
    *,
    dry_run: bool = False,
    city_fips: str = RICHMOND_FIPS,
) -> dict[str, int]:
    """Write individual speaker records to public_comments table.

    Returns stats dict with counts.
    """
    item_id_map = _get_agenda_item_ids(meeting_id)
    speakers = result.get("speakers", [])
    now = datetime.now(timezone.utc)

    stats = {
        "inserted": 0,
        "skipped_no_item": 0,
        "skipped_duplicate": 0,
        "open_forum": 0,
    }

    if not speakers:
        print(f"  No speakers to import for {meeting_date}")
        return stats

    if dry_run:
        # Preview mode
        by_item: dict[str, list[dict]] = {}
        for s in speakers:
            item = s.get("item_number", "unknown")
            by_item.setdefault(item, []).append(s)

        for item_num, item_speakers in sorted(by_item.items()):
            resolved = (
                "open_forum"
                if "open_forum" in item_num
                else _resolve_item_id(item_num, item_id_map)
            )
            marker = "Y" if resolved else "X"
            print(f"    {marker} {item_num}: {len(item_speakers)} speakers")
            for s in item_speakers[:3]:
                name = s.get("speaker_name", "?")
                conf = s.get("name_confidence", "?")
                summary = (s.get("summary") or "")[:80]
                print(f"      - {name} [{conf}] {summary}")
            if len(item_speakers) > 3:
                print(f"      ... and {len(item_speakers) - 3} more")

        stats["inserted"] = len(speakers)
        return stats

    conn = get_connection()

    for s in speakers:
        item_number = s.get("item_number", "")
        speaker_name = (s.get("speaker_name") or "").strip()
        method = s.get("method", "in_person")
        summary = (s.get("summary") or "").strip()
        name_confidence = s.get("name_confidence", "high")

        if not speaker_name:
            continue

        # Resolve agenda item
        is_open_forum = "open_forum" in item_number.lower()
        agenda_item_id = None

        if is_open_forum:
            stats["open_forum"] += 1
        else:
            agenda_item_id = _resolve_item_id(item_number, item_id_map)
            if not agenda_item_id:
                print(f"    SKIP {speaker_name} on {item_number}: item not found")
                stats["skipped_no_item"] += 1
                continue

        # Normalize method
        if method not in ("in_person", "zoom", "phone"):
            method = "in_person"

        with conn.cursor() as cur:
            try:
                cur.execute(
                    """INSERT INTO public_comments
                       (meeting_id, agenda_item_id, speaker_name, method, summary,
                        comment_type, source, confidence, name_confidence,
                        extracted_at, city_fips)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (meeting_id, COALESCE(agenda_item_id::text, ''),
                                    COALESCE(speaker_name, ''), COALESCE(summary, ''))
                       DO NOTHING""",
                    (
                        meeting_id,
                        agenda_item_id,
                        speaker_name,
                        method,
                        summary or None,
                        "public",
                        SOURCE_YOUTUBE,
                        1.0,
                        name_confidence,
                        now,
                        city_fips,
                    ),
                )
                if cur.rowcount > 0:
                    stats["inserted"] += 1
                else:
                    stats["skipped_duplicate"] += 1
            except Exception as e:
                print(f"    ERROR inserting {speaker_name}: {e}")
                conn.rollback()
                continue

    conn.commit()
    conn.close()

    print(
        f"  Imported: {stats['inserted']} speakers, "
        f"{stats['open_forum']} open forum, "
        f"{stats['skipped_no_item']} unmatched items, "
        f"{stats['skipped_duplicate']} duplicates"
    )
    return stats


# -- Commands -------------------------------------------------


def cmd_extract(
    meeting_date: str | None = None,
    *,
    dry_run: bool = False,
    limit: int | None = None,
    force: bool = False,
) -> None:
    """Extract individual speakers from transcripts and import to DB."""
    meetings = _meetings_needing_extraction(
        meeting_date=meeting_date,
        include_already_extracted=force,
    )

    if meeting_date and not meetings:
        print(f"No transcript found for {meeting_date}, or already extracted (use --force)")
        sys.exit(1)

    if limit:
        meetings = meetings[:limit]

    if not meetings:
        print("All meetings with transcripts already have community voice data.")
        return

    _ensure_dirs()

    total_speakers = 0
    total_cost = 0.0

    print(f"Extracting community voice for {len(meetings)} meetings...")
    if dry_run:
        print("[DRY RUN — no DB writes]\n")
    else:
        print()

    for m in meetings:
        date = m["meeting_date"]
        print(f"\n-- {date} ({m['item_count']} items) --")

        result = extract_speakers(m["transcript_path"], m["meeting_id"], date)
        if not result:
            continue

        # Save raw result for audit
        result_path = RESULTS_DIR / f"{date}_community_voice.json"
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        stats = import_speakers(
            result, m["meeting_id"], date, dry_run=dry_run,
        )
        total_speakers += stats["inserted"]

    print(f"\n{'=' * 50}")
    print(
        f"{'[DRY RUN] ' if dry_run else ''}"
        f"Complete: {total_speakers} speakers across {len(meetings)} meetings"
    )


def cmd_status(city_fips: str = RICHMOND_FIPS) -> None:
    """Show community voice extraction coverage."""
    conn = get_connection()

    with conn.cursor() as cur:
        # Total transcripts available
        transcript_count = sum(
            1
            for p in TRANSCRIPT_DIR.glob("*_clean.txt")
            if re.match(r"\d{4}-\d{2}-\d{2}", p.stem.replace("_clean", ""))
        ) if TRANSCRIPT_DIR.exists() else 0

        # Meetings with transcript-sourced comments
        cur.execute(
            """SELECT COUNT(DISTINCT meeting_id)
               FROM public_comments
               WHERE source = %s AND city_fips = %s""",
            (SOURCE_YOUTUBE, city_fips),
        )
        extracted_meetings = cur.fetchone()[0]

        # Total transcript-sourced comments
        cur.execute(
            """SELECT COUNT(*)
               FROM public_comments
               WHERE source = %s AND city_fips = %s""",
            (SOURCE_YOUTUBE, city_fips),
        )
        total_comments = cur.fetchone()[0]

        # Comments by name confidence
        cur.execute(
            """SELECT name_confidence, COUNT(*)
               FROM public_comments
               WHERE source = %s AND city_fips = %s
               GROUP BY name_confidence
               ORDER BY name_confidence""",
            (SOURCE_YOUTUBE, city_fips),
        )
        by_confidence = cur.fetchall()

        # Meetings needing extraction
        needs = _meetings_needing_extraction(city_fips=city_fips)

    conn.close()

    print("Community Voice Extraction Status")
    print("=" * 40)
    print(f"  Transcripts available:  {transcript_count}")
    print(f"  Meetings extracted:     {extracted_meetings}")
    print(f"  Meetings remaining:     {len(needs)}")
    print(f"  Total speaker records:  {total_comments}")

    if by_confidence:
        print("\n  Name confidence:")
        for conf, count in by_confidence:
            print(f"    {conf or 'null':>8}: {count}")

    if needs:
        print(f"\n  Next {min(5, len(needs))} to extract:")
        for m in needs[:5]:
            print(f"    {m['meeting_date']}  ({m['item_count']} items)")


# -- CLI ------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Community Voice: extract individual speakers from transcripts"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Extract
    extract_parser = subparsers.add_parser(
        "extract", help="Extract speakers via LLM and import to DB"
    )
    extract_parser.add_argument("--meeting-date", help="Single date (YYYY-MM-DD)")
    extract_parser.add_argument(
        "--dry-run", action="store_true", help="Preview without DB writes"
    )
    extract_parser.add_argument("--limit", type=int, help="Limit number of meetings")
    extract_parser.add_argument(
        "--force", action="store_true", help="Re-extract even if already done"
    )

    # Status
    subparsers.add_parser("status", help="Show extraction coverage")

    args = parser.parse_args()

    if args.command == "extract":
        cmd_extract(
            args.meeting_date,
            dry_run=args.dry_run,
            limit=args.limit,
            force=args.force,
        )
    elif args.command == "status":
        cmd_status()


if __name__ == "__main__":
    main()
