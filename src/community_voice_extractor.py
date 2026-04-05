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
from text_utils import normalize_item_number, resolve_item_id  # noqa: E402

# -- Constants ------------------------------------------------

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 16000  # Increased from 8000 — large meetings need room for 200+ speakers

TRANSCRIPT_DIR = Path(__file__).parent.parent / "data" / "transcripts"
PROMPT_PATH = Path(__file__).parent / "prompts" / "community_voice_system.txt"
RESULTS_DIR = TRANSCRIPT_DIR / "community_voice"

SOURCE_YOUTUBE = "youtube_transcript"
SOURCE_GRANICUS = "granicus_transcript"

BATCH_DIR = TRANSCRIPT_DIR / "community_voice_batch"


def _ensure_dirs() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    BATCH_DIR.mkdir(parents=True, exist_ok=True)


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


# Item resolution delegated to shared text_utils module.
_normalize_item_number = normalize_item_number
_resolve_item_id = resolve_item_id


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


def _strip_json_fences(text: str) -> str:
    """Remove markdown code fences from JSON output."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()
    return text


def _call_api(
    client: Any,
    system_prompt: str,
    messages: list[dict[str, str]],
) -> tuple[Any, float]:
    """Make a single Claude API call, return (response, cost)."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=messages,
    )
    cost = (
        response.usage.input_tokens * 0.003 / 1000
        + response.usage.output_tokens * 0.015 / 1000
    )
    print(
        f"  API response: {response.usage.input_tokens:,} in / "
        f"{response.usage.output_tokens:,} out (${cost:.3f})"
        f"  stop_reason={response.stop_reason}"
    )
    return response, cost


def extract_speakers(
    transcript_path: Path,
    meeting_id: str,
    meeting_date: str,
) -> dict[str, Any] | None:
    """Send transcript to Claude API and extract individual speakers.

    For long transcripts that exceed MAX_TOKENS, uses continuation calls
    to get all speakers. The model is asked to continue its truncated JSON
    output until all speakers are extracted.

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
    messages: list[dict[str, str]] = [{"role": "user", "content": user_prompt}]

    response, total_cost = _call_api(client, system_prompt, messages)
    accumulated_text = response.content[0].text

    # Continuation loop: if truncated, ask the model to continue
    max_continuations = 5
    continuation = 0
    while response.stop_reason == "max_tokens" and continuation < max_continuations:
        continuation += 1
        print(f"  Response truncated — sending continuation {continuation}...")

        # Build conversation with the truncated output so far
        messages = [
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": accumulated_text},
            {"role": "user", "content": "Continue the JSON output exactly where you left off. Do not repeat any speakers already listed. Output only the remaining JSON."},
        ]
        response, cost = _call_api(client, system_prompt, messages)
        total_cost += cost
        accumulated_text += response.content[0].text

    if continuation > 0:
        print(f"  Total cost across {continuation + 1} calls: ${total_cost:.3f}")

    # Parse JSON — strip markdown fences if present
    text = _strip_json_fences(accumulated_text)

    # If we had continuations, the JSON might be split across calls.
    # Try parsing as-is first, then try to repair by extracting all speaker objects.
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        # Attempt repair: extract all {...} speaker objects from the text
        result = _repair_continued_json(text)
        if result is None:
            print(f"  ERROR: Failed to parse JSON even after repair")
            print(f"  Raw response (first 500): {text[:500]}")
            print(f"  Raw response (last 500): {text[-500:]}")
            return None

    speakers = result.get("speakers", [])
    print(f"  Extracted {len(speakers)} speaker entries")

    return result


def _repair_continued_json(text: str) -> dict[str, Any] | None:
    """Attempt to repair JSON that was split across continuation calls.

    Extracts all speaker-like objects from the text even if the overall
    JSON structure is broken.
    """
    # Strategy 1: Find the speakers array and close it properly
    # Look for {"speakers": [...
    match = re.search(r'\{\s*"speakers"\s*:\s*\[', text)
    if not match:
        return None

    # Find all complete speaker objects using bracket matching
    speakers: list[dict[str, Any]] = []
    pos = match.end()
    depth = 0
    obj_start = -1

    while pos < len(text):
        ch = text[pos]
        if ch == '{' and depth == 0:
            obj_start = pos
            depth = 1
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and obj_start >= 0:
                try:
                    obj = json.loads(text[obj_start:pos + 1])
                    if "speaker_name" in obj or "name" in obj:
                        speakers.append(obj)
                except json.JSONDecodeError:
                    pass
                obj_start = -1
        pos += 1

    if speakers:
        print(f"  Repaired JSON: recovered {len(speakers)} speaker objects")
        return {"speakers": speakers}

    return None


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
        # "closed_session" comments are public comments made before closed session —
        # still public record, stored with agenda_item_id=NULL like open forum.
        is_unlinked = ("open_forum" in item_number.lower()
                       or "closed_session" in item_number.lower())
        agenda_item_id = None

        if is_unlinked:
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


def _find_incomplete_meetings(
    city_fips: str = RICHMOND_FIPS,
    min_gap_ratio: float = 2.0,
) -> list[dict[str, Any]]:
    """Find meetings where theme narratives suggest more speakers than extracted.

    Returns meetings where themed comment count exceeds extracted rows by
    at least min_gap_ratio, indicating truncated extraction.
    """
    conn = get_connection()

    with conn.cursor() as cur:
        cur.execute(
            """WITH extracted AS (
                SELECT pc.meeting_id, ai.id as agenda_item_id,
                       count(*) as extracted_count
                FROM public_comments pc
                JOIN agenda_items ai ON pc.agenda_item_id = ai.id
                WHERE pc.city_fips = %s AND pc.source = %s
                GROUP BY pc.meeting_id, ai.id
            ),
            themed AS (
                SELECT itn.agenda_item_id, sum(itn.comment_count) as themed_count
                FROM item_theme_narratives itn
                JOIN agenda_items ai ON itn.agenda_item_id = ai.id
                JOIN meetings m ON ai.meeting_id = m.id
                WHERE m.city_fips = %s
                GROUP BY itn.agenda_item_id
            )
            SELECT m.id as meeting_id, m.meeting_date,
                   sum(COALESCE(e.extracted_count, 0)) as total_extracted,
                   sum(t.themed_count) as total_themed,
                   (SELECT count(*) FROM agenda_items WHERE meeting_id = m.id) as item_count
            FROM themed t
            JOIN agenda_items ai ON t.agenda_item_id = ai.id
            JOIN meetings m ON ai.meeting_id = m.id
            LEFT JOIN extracted e ON e.agenda_item_id = t.agenda_item_id
            GROUP BY m.id, m.meeting_date
            HAVING sum(t.themed_count) > sum(COALESCE(e.extracted_count, 0)) * %s
            ORDER BY sum(t.themed_count) DESC""",
            (city_fips, SOURCE_YOUTUBE, city_fips, min_gap_ratio),
        )
        rows = cur.fetchall()

    conn.close()

    meetings = []
    for row in rows:
        meeting_id, meeting_date, extracted, themed, item_count = row
        date_str = str(meeting_date)
        transcript_path = TRANSCRIPT_DIR / f"{date_str}_clean.txt"
        if not transcript_path.exists():
            continue
        meetings.append({
            "meeting_id": str(meeting_id),
            "meeting_date": date_str,
            "item_count": item_count,
            "transcript_path": transcript_path,
            "extracted_count": extracted,
            "themed_count": themed,
        })

    return meetings


def _clear_meeting_comments(meeting_id: str, source: str = SOURCE_YOUTUBE) -> int:
    """Delete existing transcript-sourced comments for a meeting before re-extraction."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM public_comments WHERE meeting_id = %s AND source = %s",
            (meeting_id, source),
        )
        deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted


def _update_comment_counts(meeting_id: str) -> None:
    """Sync public_comment_count on agenda_items from actual public_comments rows."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE agenda_items ai
               SET public_comment_count = sub.cnt
               FROM (
                   SELECT agenda_item_id, count(*) as cnt
                   FROM public_comments
                   WHERE meeting_id = %s AND agenda_item_id IS NOT NULL
                   GROUP BY agenda_item_id
               ) sub
               WHERE ai.id = sub.agenda_item_id""",
            (meeting_id,),
        )
        updated = cur.rowcount
    conn.commit()
    conn.close()
    print(f"  Updated comment counts on {updated} agenda items")


def cmd_extract(
    meeting_date: str | None = None,
    *,
    dry_run: bool = False,
    limit: int | None = None,
    force: bool = False,
    rerun_incomplete: bool = False,
) -> None:
    """Extract individual speakers from transcripts and import to DB."""
    if rerun_incomplete:
        meetings = _find_incomplete_meetings()
        if not meetings:
            print("No meetings with incomplete extraction found.")
            return
        print(f"Found {len(meetings)} meetings with incomplete extraction:")
        for m in meetings:
            print(
                f"  {m['meeting_date']}: {m['extracted_count']} extracted vs "
                f"{m['themed_count']} themed"
            )
        print()
    else:
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

        # For re-extraction, clear old data first
        if rerun_incomplete and not dry_run:
            deleted = _clear_meeting_comments(m["meeting_id"])
            print(f"  Cleared {deleted} old comment records")

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

        # Update comment counts on agenda items
        if not dry_run:
            _update_comment_counts(m["meeting_id"])

    print(f"\n{'=' * 50}")
    print(
        f"{'[DRY RUN] ' if dry_run else ''}"
        f"Complete: {total_speakers} speakers across {len(meetings)} meetings"
    )


def cmd_batch_submit(
    meeting_date: str | None = None,
    *,
    limit: int | None = None,
    rerun_incomplete: bool = False,
) -> None:
    """Submit extraction requests as an Anthropic Batch API job.

    Creates a JSONL request file and submits it. Results are retrieved
    later with batch-import once the batch completes.
    """
    if anthropic is None:
        print("ERROR: anthropic package required. Run: pip install anthropic")
        sys.exit(1)

    if rerun_incomplete:
        meetings = _find_incomplete_meetings()
        if not meetings:
            print("No meetings with incomplete extraction found.")
            return
        print(f"Found {len(meetings)} meetings with incomplete extraction")
    else:
        meetings = _meetings_needing_extraction(
            meeting_date=meeting_date,
            include_already_extracted=False,
        )

    if limit:
        meetings = meetings[:limit]

    if not meetings:
        print("No meetings to process.")
        return

    _ensure_dirs()
    system_prompt = _load_system_prompt()

    # Build JSONL request file
    requests = []
    for m in meetings:
        transcript = m["transcript_path"].read_text(encoding="utf-8")
        agenda_text = _get_agenda_items_text(m["meeting_id"])

        user_prompt = (
            f"AGENDA ITEMS FOR THIS MEETING ({m['meeting_date']}):\n"
            f"{agenda_text}\n\n"
            f"TRANSCRIPT:\n{transcript}\n\n"
            f"Extract every individual public comment speaker with their name, "
            f"method, agenda item, and a 1-3 sentence summary of what they said. "
            f"Return JSON."
        )

        requests.append({
            "custom_id": f"{m['meeting_date']}_{m['meeting_id'][:8]}",
            "params": {
                "model": MODEL,
                "max_tokens": MAX_TOKENS,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            },
        })

    # Write JSONL
    jsonl_path = BATCH_DIR / "batch_request.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for req in requests:
            f.write(json.dumps(req) + "\n")

    print(f"Created batch request: {jsonl_path} ({len(requests)} requests)")

    # Also save meeting metadata for import step
    meta_path = BATCH_DIR / "batch_meetings.json"
    meta = {m["meeting_date"]: {
        "meeting_id": m["meeting_id"],
        "item_count": int(m["item_count"]),
        "extracted_count": int(m.get("extracted_count") or 0),
        "themed_count": int(m.get("themed_count") or 0),
    } for m in meetings}
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # Submit batch
    client = anthropic.Anthropic()
    batch = client.messages.batches.create(
        requests=[
            {
                "custom_id": req["custom_id"],
                "params": {
                    "model": req["params"]["model"],
                    "max_tokens": req["params"]["max_tokens"],
                    "system": req["params"]["system"],
                    "messages": req["params"]["messages"],
                },
            }
            for req in requests
        ]
    )

    print(f"\nBatch submitted: {batch.id}")
    print(f"Status: {batch.processing_status}")

    # Save batch ID for retrieval
    batch_id_path = BATCH_DIR / "batch_id.txt"
    batch_id_path.write_text(batch.id, encoding="utf-8")
    print(f"Batch ID saved to {batch_id_path}")
    print(f"\nRun 'python community_voice_extractor.py batch-import' once the batch completes.")
    print(f"Check status: python -c \"import anthropic; print(anthropic.Anthropic().messages.batches.retrieve('{batch.id}').processing_status)\"")


def cmd_batch_import() -> None:
    """Import results from a completed Anthropic Batch API job."""
    if anthropic is None:
        print("ERROR: anthropic package required. Run: pip install anthropic")
        sys.exit(1)

    batch_id_path = BATCH_DIR / "batch_id.txt"
    if not batch_id_path.exists():
        print("No batch ID found. Run batch-submit first.")
        sys.exit(1)

    batch_id = batch_id_path.read_text(encoding="utf-8").strip()
    meta_path = BATCH_DIR / "batch_meetings.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    client = anthropic.Anthropic()
    batch = client.messages.batches.retrieve(batch_id)

    print(f"Batch {batch_id}: {batch.processing_status}")
    print(f"  Succeeded: {batch.request_counts.succeeded}")
    print(f"  Errored: {batch.request_counts.errored}")
    print(f"  Expired: {batch.request_counts.expired}")
    print(f"  Processing: {batch.request_counts.processing}")

    if batch.processing_status != "ended":
        print(f"\nBatch not yet complete. Current status: {batch.processing_status}")
        print("Try again later.")
        return

    # Stream results
    total_speakers = 0
    total_imported = 0

    for result in client.messages.batches.results(batch_id):
        custom_id = result.custom_id
        meeting_date = custom_id.split("_")[0]

        meeting_meta = meta.get(meeting_date)
        if not meeting_meta:
            print(f"  WARN: No metadata for {custom_id}, skipping")
            continue

        meeting_id = meeting_meta["meeting_id"]

        if result.result.type == "errored":
            print(f"  ERROR for {meeting_date}: {result.result.error}")
            continue

        if result.result.type == "expired":
            print(f"  EXPIRED for {meeting_date}")
            continue

        message = result.result.message
        text = message.content[0].text
        text = _strip_json_fences(text)

        truncated = message.stop_reason == "max_tokens"
        if truncated:
            print(f"  WARN: {meeting_date} was truncated — attempting repair")

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = _repair_continued_json(text)
            if parsed is None:
                print(f"  ERROR: Could not parse result for {meeting_date}")
                continue

        speakers = parsed.get("speakers", [])
        print(f"\n-- {meeting_date}: {len(speakers)} speakers --")

        # Save raw result
        result_path = RESULTS_DIR / f"{meeting_date}_community_voice.json"
        result_path.write_text(json.dumps(parsed, indent=2), encoding="utf-8")

        # Clear old data and import
        deleted = _clear_meeting_comments(meeting_id)
        if deleted:
            print(f"  Cleared {deleted} old records")

        stats = import_speakers(parsed, meeting_id, meeting_date)
        total_speakers += len(speakers)
        total_imported += stats["inserted"]

        # Update counts
        _update_comment_counts(meeting_id)

    print(f"\n{'=' * 50}")
    print(f"Complete: {total_imported} speakers imported from {batch.request_counts.succeeded} meetings")
    print(f"(Total extracted: {total_speakers})")


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
    extract_parser.add_argument(
        "--rerun-incomplete", action="store_true",
        help="Find and re-extract meetings where theme data suggests truncated output"
    )

    # Batch submit
    batch_submit_parser = subparsers.add_parser(
        "batch-submit", help="Submit extraction as Anthropic Batch API job (50% cheaper)"
    )
    batch_submit_parser.add_argument("--meeting-date", help="Single date (YYYY-MM-DD)")
    batch_submit_parser.add_argument("--limit", type=int, help="Limit number of meetings")
    batch_submit_parser.add_argument(
        "--rerun-incomplete", action="store_true",
        help="Find and re-extract meetings with truncated output"
    )

    # Batch import
    subparsers.add_parser(
        "batch-import", help="Import results from a completed batch job"
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
            rerun_incomplete=args.rerun_incomplete,
        )
    elif args.command == "batch-submit":
        cmd_batch_submit(
            args.meeting_date,
            limit=args.limit,
            rerun_incomplete=args.rerun_incomplete,
        )
    elif args.command == "batch-import":
        cmd_batch_import()
    elif args.command == "status":
        cmd_status()


if __name__ == "__main__":
    main()
