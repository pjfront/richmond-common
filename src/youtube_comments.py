"""
S20: YouTube transcript pipeline for public comment speaker counts.

Extracts per-item public comment speaker counts from KCRT TV YouTube
recordings of Richmond City Council meetings. One Claude API call per
meeting transcript, returns speaker count + methods per agenda item.

Workflow:
  1. Discover:  Match KCRT YouTube videos to meetings by date
  2. Fetch:     Download auto-generated VTT captions via yt-dlp
  3. Extract:   Send transcript + agenda items to Claude API
  4. Import:    Write speaker counts to agenda_items.public_comment_count

Usage:
  python youtube_comments.py discover                # List available videos
  python youtube_comments.py fetch                   # Download transcripts
  python youtube_comments.py fetch --meeting-date 2026-03-03
  python youtube_comments.py extract                 # Count speakers via LLM
  python youtube_comments.py extract --meeting-date 2026-03-03
  python youtube_comments.py extract --dry-run       # Preview without DB writes
  python youtube_comments.py run                     # Full pipeline: fetch + extract
  python youtube_comments.py run --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
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

# --Constants ------------------------------------------------

KCRT_CHANNEL_ID = "UCJ0TqQHWE4uaC7xI1TkRdRA"
KCRT_CHANNEL_URL = f"https://www.youtube.com/@KCRTTV"
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 4000

DATA_DIR = Path(__file__).parent.parent / "data"
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
PROMPT_PATH = Path(__file__).parent / "prompts" / "youtube_comments_system.txt"

# Date patterns found in KCRT video titles
# "Richmond City Council 3/3/2026" or "Richmond City Council Meeting - 3/17/2026"
DATE_PATTERN = re.compile(
    r"Richmond City Council.*?(\d{1,2})[/-](\d{1,2})[/-](\d{4})"
)


def _ensure_dirs() -> None:
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)


# --Discover -------------------------------------------------


def discover_videos() -> list[dict[str, str]]:
    """Search KCRT channel for City Council meeting videos.

    Returns list of {video_id, title, meeting_date (YYYY-MM-DD)}.
    Uses multiple search queries to maximize coverage.
    """
    import urllib.request

    all_html = ""
    queries = [
        "Richmond+City+Council",
        "Richmond+City+Council+2024",
        "Richmond+City+Council+2025",
        "Richmond+City+Council+2026",
        "Richmond+City+Council+Meeting",
    ]
    for query in queries:
        url = f"{KCRT_CHANNEL_URL}/search?query={query}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp:
            all_html += resp.read().decode("utf-8", errors="replace")

    html = all_html

    # Extract video IDs and titles from YouTube's inline JSON
    video_ids = re.findall(r'"videoId":"([^"]+)"', html)
    titles = re.findall(r'"title":\{"runs":\[\{"text":"([^"]+)"', html)

    # Deduplicate video IDs while preserving order
    seen: set[str] = set()
    videos: list[dict[str, str]] = []

    for vid, title in zip(video_ids, titles):
        if vid in seen:
            continue
        seen.add(vid)

        # Skip non-council-meeting videos
        if "city council" not in title.lower():
            continue
        if "candidate" in title.lower() or "forum" in title.lower():
            continue

        # Parse date from title
        match = DATE_PATTERN.search(title)
        if not match:
            continue

        month, day, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        meeting_date = f"{year}-{month:02d}-{day:02d}"

        videos.append({
            "video_id": vid,
            "title": title,
            "meeting_date": meeting_date,
        })

    return videos


def match_videos_to_meetings(
    videos: list[dict[str, str]],
    city_fips: str = RICHMOND_FIPS,
) -> list[dict[str, Any]]:
    """Match discovered videos to meetings in the database.

    Returns list of {video_id, title, meeting_date, meeting_id, item_count}.
    """
    conn = get_connection()
    matched: list[dict[str, Any]] = []

    with conn.cursor() as cur:
        for video in videos:
            cur.execute(
                """SELECT m.id,
                          (SELECT COUNT(*) FROM agenda_items ai WHERE ai.meeting_id = m.id) as item_count
                   FROM meetings m
                   WHERE m.city_fips = %s AND m.meeting_date = %s AND m.meeting_type = 'regular'
                   LIMIT 1""",
                (city_fips, video["meeting_date"]),
            )
            row = cur.fetchone()
            if row:
                matched.append({
                    **video,
                    "meeting_id": row[0],
                    "item_count": row[1],
                })

    conn.close()

    # Group by meeting_date, keep all video IDs per date
    by_date: dict[str, list[dict[str, Any]]] = {}
    for m in matched:
        by_date.setdefault(m["meeting_date"], []).append(m)

    # Deduplicate: keep first entry per date, store alternates
    deduped: list[dict[str, Any]] = []
    for date, entries in by_date.items():
        primary = entries[0]
        primary["alt_video_ids"] = [e["video_id"] for e in entries[1:]]
        deduped.append(primary)

    return deduped


# --Fetch ----------------------------------------------------


def _vtt_to_clean_text(vtt_path: Path) -> str:
    """Convert VTT subtitle file to deduplicated timestamped text.

    YouTube VTT has progressive-reveal cues where each cue adds a word.
    We deduplicate by skipping cues whose text is a prefix of the next cue.
    Timestamps are inserted every ~30 seconds for context.
    """
    content = vtt_path.read_text(encoding="utf-8", errors="replace")

    blocks = content.split("\n\n")
    cues: list[tuple[float, str]] = []

    for block in blocks:
        block = block.strip()
        if "-->" not in block:
            continue
        lines = block.split("\n")
        ts_line = next((l for l in lines if "-->" in l), None)
        if not ts_line:
            continue

        text_lines = [
            l for l in lines
            if "-->" not in l and l.strip() and not l.strip().isdigit()
        ]
        if not text_lines:
            continue

        # Parse start time to seconds
        start_str = ts_line.split("-->")[0].strip()
        parts = start_str.split(":")
        h, m = int(parts[0]), int(parts[1])
        s = float(parts[2])
        start_sec = h * 3600 + m * 60 + s

        # Clean text
        text = " ".join(
            re.sub(r"<[^>]+>", "", l).strip()
            for l in text_lines
            if re.sub(r"<[^>]+>", "", l).strip()
        )
        text = text.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
        if text:
            cues.append((start_sec, text))

    # Deduplicate progressive-reveal cues
    clean: list[tuple[float, str]] = []
    for i, (ts, text) in enumerate(cues):
        if i + 1 < len(cues) and text in cues[i + 1][1]:
            continue
        if not text.strip():
            continue
        clean.append((ts, text))

    # Format with timestamps every ~30 seconds
    output: list[str] = []
    last_ts = -30.0
    for ts, text in clean:
        if ts - last_ts >= 30:
            h = int(ts // 3600)
            m_val = int((ts % 3600) // 60)
            s_val = int(ts % 60)
            output.append(f"\n[{h}:{m_val:02d}:{s_val:02d}]")
            last_ts = ts
        output.append(text)

    return "\n".join(output)


def _try_download_vtt(video_id: str, meeting_date: str) -> Path | None:
    """Attempt to download VTT subtitles for a single video ID.

    Returns VTT path if successful, None if no subtitles available.
    """
    vtt_path = TRANSCRIPT_DIR / f"{meeting_date}.en.vtt"

    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--write-auto-sub",
                "--sub-lang", "en",
                "--sub-format", "vtt",
                "--skip-download",
                "-o", str(vtt_path).replace(".en.vtt", ""),
            ] + [f"https://www.youtube.com/watch?v={video_id}"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        print("  ERROR: yt-dlp not installed. Run: pip install yt-dlp")
        return None
    except subprocess.TimeoutExpired:
        print(f"  ERROR: yt-dlp timed out for {video_id}")
        return None

    # Check if "no subtitles" in output
    if "no subtitles" in result.stderr.lower() or "no subtitles" in result.stdout.lower():
        return None

    if vtt_path.exists():
        return vtt_path

    # Try alternate naming
    candidates = list(TRANSCRIPT_DIR.glob(f"{meeting_date}*.vtt"))
    return candidates[0] if candidates else None


def _try_transcript_api(video_id: str, meeting_date: str) -> Path | None:
    """Fallback: fetch transcript via youtube-transcript-api.

    This works for livestream recordings where yt-dlp can't access
    auto-generated captions. The youtube-transcript-api accesses the
    same transcript shown in YouTube's "Show transcript" panel.

    Returns path to clean text file, or None on failure.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        print("  youtube-transcript-api not installed. Run: pip install youtube-transcript-api")
        return None

    print(f"  Trying youtube-transcript-api for {video_id}...")
    try:
        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id, languages=["en"])
    except Exception as e:
        print(f"    youtube-transcript-api failed: {e}")
        return None

    if not transcript.snippets:
        print(f"    No transcript snippets returned")
        return None

    # Convert to timestamped clean text (same format as _vtt_to_clean_text)
    output: list[str] = []
    last_ts = -30.0

    for snippet in transcript.snippets:
        ts = snippet.start
        text = snippet.text.strip()
        if not text:
            continue

        if ts - last_ts >= 30:
            h = int(ts // 3600)
            m_val = int((ts % 3600) // 60)
            s_val = int(ts % 60)
            output.append(f"\n[{h}:{m_val:02d}:{s_val:02d}]")
            last_ts = ts
        output.append(text)

    clean_text = "\n".join(output)

    if not clean_text.strip():
        print(f"    Transcript empty after processing")
        return None

    youtube_path = TRANSCRIPT_DIR / f"{meeting_date}_youtube.txt"
    youtube_path.write_text(clean_text, encoding="utf-8")

    # Also write _clean.txt for backward compat (if no Granicus version exists)
    clean_path = TRANSCRIPT_DIR / f"{meeting_date}_clean.txt"
    granicus_path = TRANSCRIPT_DIR / f"{meeting_date}_granicus.txt"
    if not granicus_path.exists():
        clean_path.write_text(clean_text, encoding="utf-8")

    chars = len(clean_text)
    est_tokens = chars // 4
    print(f"  Clean transcript (via API): {chars:,} chars (~{est_tokens:,} tokens)")

    return youtube_path


def fetch_transcript(
    video_id: str,
    meeting_date: str,
    alt_video_ids: list[str] | None = None,
) -> Path | None:
    """Download YouTube auto-generated transcript.

    Tries yt-dlp first (works for regular uploads), then falls back to
    youtube-transcript-api (works for livestream recordings where yt-dlp
    can't access auto-generated captions).

    Returns path to clean text file, or None on failure.
    """
    _ensure_dirs()

    youtube_path = TRANSCRIPT_DIR / f"{meeting_date}_youtube.txt"
    clean_path = TRANSCRIPT_DIR / f"{meeting_date}_clean.txt"

    # Skip if already fetched
    if youtube_path.exists():
        print(f"  Transcript already exists: {youtube_path.name}")
        return youtube_path

    # Try primary video, then alternates
    all_ids = [video_id] + (alt_video_ids or [])
    vtt_path = None

    for vid in all_ids:
        print(f"  Trying {vid} for {meeting_date}...")
        vtt_path = _try_download_vtt(vid, meeting_date)
        if vtt_path:
            break
        print(f"    No subtitles on {vid}")

    if not vtt_path:
        # Fallback: try youtube-transcript-api (works for livestream recordings)
        result_path = _try_transcript_api(video_id, meeting_date)
        if result_path:
            return result_path
        print(f"  ERROR: No transcript found for {meeting_date} via yt-dlp or transcript API")
        return None

    # Convert to clean text
    print(f"  Converting VTT to clean text...")
    clean_text = _vtt_to_clean_text(vtt_path)
    youtube_path.write_text(clean_text, encoding="utf-8")

    # Also write _clean.txt for backward compat (if no Granicus version exists)
    granicus_path = TRANSCRIPT_DIR / f"{meeting_date}_granicus.txt"
    if not granicus_path.exists():
        clean_path.write_text(clean_text, encoding="utf-8")

    chars = len(clean_text)
    est_tokens = chars // 4
    print(f"  Clean transcript: {chars:,} chars (~{est_tokens:,} tokens)")

    return youtube_path


# --Extract --------------------------------------------------


def _load_system_prompt() -> str:
    """Load the system prompt for comment extraction."""
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding="utf-8").strip()

    # Inline fallback
    return """You are analyzing a city council meeting transcript to count public comment speakers per agenda item.

For each agenda item that had public comments, return:
- item_number: the agenda item number exactly as listed (e.g. "W.1", "U.2.a")
- speaker_count: how many distinct people spoke during public comment on this item
- methods: array of comment methods observed ("in_person", "zoom", "phone")

Also return open_forum speakers separately (general public comment period, not on a specific item).

RULES:
1. Only count speakers during PUBLIC COMMENT periods, not council discussion or staff presentations
2. The chair typically announces "we have N speakers" or "public comment is open" before each period
3. Count each person once per item even if they speak multiple times
4. Distinguish open forum (general) from item-specific public comment
5. Include all methods: in_person, zoom, phone
6. If you cannot determine the exact count, use the chair's announced count as your best estimate

Return valid JSON only. No markdown, no explanation."""


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

    return {r[0]: r[1] for r in rows}


def extract_speakers(
    transcript_path: Path,
    meeting_id: str,
    meeting_date: str,
) -> dict[str, Any] | None:
    """Send transcript to Claude API and extract speaker counts per item.

    Returns parsed JSON result or None on failure.
    """
    if anthropic is None:
        print("ERROR: anthropic package required. Run: pip install anthropic")
        return None

    transcript = transcript_path.read_text(encoding="utf-8")
    agenda_text = _get_agenda_items_text(meeting_id)
    system_prompt = _load_system_prompt()

    user_prompt = f"""AGENDA ITEMS FOR {meeting_date}:
{agenda_text}

TRANSCRIPT:
{transcript}

Count public comment speakers for each agenda item. Return JSON:
{{
  "open_forum": {{ "speaker_count": N, "methods": ["in_person", "zoom", ...] }},
  "items": [
    {{ "item_number": "X.1", "speaker_count": N, "methods": ["in_person"] }}
  ]
}}"""

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
    cost = response.usage.input_tokens * 0.003 / 1000 + response.usage.output_tokens * 0.015 / 1000

    print(f"  API response: {response.usage.input_tokens:,} in / {response.usage.output_tokens:,} out (${cost:.3f})")

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

    return result


def import_speaker_counts(
    result: dict[str, Any],
    meeting_id: str,
    meeting_date: str,
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    """Write speaker counts to agenda_items.public_comment_count.

    Returns stats dict with counts of updates.
    """
    item_id_map = _get_agenda_item_ids(meeting_id)
    stats = {"updated": 0, "not_found": 0, "open_forum": 0}

    items = result.get("items", [])
    open_forum = result.get("open_forum", {})

    if open_forum.get("speaker_count", 0) > 0:
        stats["open_forum"] = open_forum["speaker_count"]

    print(f"\n  Meeting {meeting_date}: {len(items)} items with comments, {stats['open_forum']} open forum speakers")

    if not dry_run:
        conn = get_connection()

    for item in items:
        item_number = item.get("item_number", "")
        count = item.get("speaker_count", 0)
        methods = item.get("methods", [])

        if count == 0:
            continue

        # Try exact match first, then fuzzy matching
        agenda_item_id = item_id_map.get(item_number)
        if not agenda_item_id:
            # Normalize: lowercase, insert dots between letter-number boundaries
            # "P5" -> "P.5", "N3D" -> "N.3.D", "V6a" -> "V.6.a"
            def normalize_item_num(s: str) -> str:
                s = s.strip().upper()
                # Insert dots between letter->digit and digit->letter transitions
                result = re.sub(r'([A-Z])(\d)', r'\1.\2', s)
                result = re.sub(r'(\d)([A-Z])', r'\1.\2', result)
                return result.lower()

            norm_input = normalize_item_num(item_number)
            for db_num, db_id in item_id_map.items():
                if normalize_item_num(db_num) == norm_input:
                    agenda_item_id = db_id
                    break

        if not agenda_item_id:
            print(f"    SKIP {item_number}: {count} speakers — item not found in DB")
            stats["not_found"] += 1
            continue

        method_str = ", ".join(methods)
        print(f"    {item_number}: {count} speakers ({method_str})")

        if not dry_run:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE agenda_items SET public_comment_count = %s WHERE id = %s",
                    (count, agenda_item_id),
                )
            stats["updated"] += 1

    if not dry_run:
        conn.commit()
        conn.close()

    return stats


# --Pipeline Commands ----------------------------------------


def cmd_discover() -> None:
    """Discover and list available KCRT videos."""
    print("Searching KCRT TV channel for City Council meetings...\n")

    videos = discover_videos()
    matched = match_videos_to_meetings(videos)

    # Also get meetings that already have YouTube-sourced counts
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """SELECT m.meeting_date
               FROM meetings m
               JOIN agenda_items ai ON ai.meeting_id = m.id
               WHERE m.city_fips = %s AND ai.public_comment_count > 0
               GROUP BY m.meeting_date""",
            (RICHMOND_FIPS,),
        )
        dates_with_counts = {r[0].isoformat() if hasattr(r[0], 'isoformat') else str(r[0]) for r in cur.fetchall()}
    conn.close()

    print(f"Found {len(videos)} videos, {len(matched)} matched to DB meetings:\n")
    for m in matched:
        has_counts = "Y" if m["meeting_date"] in dates_with_counts else " "
        print(f"  [{has_counts}] {m['meeting_date']}  {m['item_count']:2d} items  {m['video_id']}  {m['title']}")

    unmatched = [v for v in videos if not any(m["video_id"] == v["video_id"] for m in matched)]
    if unmatched:
        print(f"\n  {len(unmatched)} videos not matched to meetings:")
        for v in unmatched:
            print(f"      {v['meeting_date']}  {v['title']}")


def cmd_fetch(meeting_date: str | None = None) -> None:
    """Download transcripts for all matched meetings (or one specific date)."""
    videos = discover_videos()
    matched = match_videos_to_meetings(videos)

    if meeting_date:
        matched = [m for m in matched if m["meeting_date"] == meeting_date]
        if not matched:
            print(f"No matched video found for {meeting_date}")
            sys.exit(1)

    print(f"Fetching transcripts for {len(matched)} meetings...\n")

    for m in matched:
        result = fetch_transcript(
            m["video_id"], m["meeting_date"],
            alt_video_ids=m.get("alt_video_ids", []),
        )
        if result:
            print(f"  OK {m['meeting_date']}")
        else:
            print(f"  FAIL {m['meeting_date']}")


def _meetings_from_local_transcripts(
    city_fips: str = RICHMOND_FIPS,
) -> list[dict[str, Any]]:
    """Build meeting list from locally available transcripts (bypass YouTube)."""
    if not TRANSCRIPT_DIR.exists():
        return []

    conn = get_connection()
    meetings: list[dict[str, Any]] = []

    for path in sorted(TRANSCRIPT_DIR.glob("*_clean.txt")) + sorted(TRANSCRIPT_DIR.glob("*_youtube.txt")):
        # Extract date from filename (YYYY-MM-DD_clean.txt or YYYY-MM-DD_youtube.txt)
        name = path.stem.replace("_clean", "").replace("_youtube", "")
        if not re.match(r"\d{4}-\d{2}-\d{2}", name):
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
            if row:
                meetings.append({
                    "meeting_date": name,
                    "meeting_id": row[0],
                    "item_count": row[1],
                    "video_id": "local",
                })

    conn.close()
    return meetings


def cmd_extract(
    meeting_date: str | None = None,
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> None:
    """Extract speaker counts from transcripts and import to DB.

    Prefers locally available transcripts over YouTube discovery
    to avoid non-deterministic search results.
    """
    # Use local transcripts if available, fall back to YouTube discovery
    matched = _meetings_from_local_transcripts()
    if not matched:
        videos = discover_videos()
        matched = match_videos_to_meetings(videos)

    if meeting_date:
        matched = [m for m in matched if m["meeting_date"] == meeting_date]
        if not matched:
            print(f"No transcript or matched video found for {meeting_date}")
            sys.exit(1)

    if limit:
        matched = matched[:limit]

    total_cost = 0.0
    total_updated = 0
    total_open_forum = 0

    print(f"Extracting speaker counts for {len(matched)} meetings...")
    if dry_run:
        print("[DRY RUN — no DB writes]\n")
    else:
        print()

    for m in matched:
        date = m["meeting_date"]
        clean_path = TRANSCRIPT_DIR / f"{date}_clean.txt"

        if not clean_path.exists():
            print(f"\n  {date}: No transcript — run 'fetch' first")
            continue

        print(f"\n--{date} ({m['item_count']} items) --")

        result = extract_speakers(clean_path, m["meeting_id"], date)
        if not result:
            continue

        # Save raw result for audit
        result_path = TRANSCRIPT_DIR / f"{date}_result.json"
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        stats = import_speaker_counts(
            result, m["meeting_id"], date, dry_run=dry_run,
        )

        total_updated += stats["updated"]
        total_open_forum += stats["open_forum"]

    print(f"\n{'=' * 50}")
    print(f"{'[DRY RUN] ' if dry_run else ''}Complete: {total_updated} items updated, {total_open_forum} open forum speakers counted")


def cmd_run(
    meeting_date: str | None = None,
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> None:
    """Full pipeline: fetch transcripts + extract speaker counts."""
    cmd_fetch(meeting_date)
    print("\n" + "=" * 50 + "\n")
    cmd_extract(meeting_date, dry_run=dry_run, limit=limit)


# --CLI ------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="YouTube transcript pipeline for public comment speaker counts"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Discover
    subparsers.add_parser("discover", help="List available KCRT meeting videos")

    # Fetch
    fetch_parser = subparsers.add_parser("fetch", help="Download transcripts")
    fetch_parser.add_argument("--meeting-date", help="Single date (YYYY-MM-DD)")

    # Extract
    extract_parser = subparsers.add_parser("extract", help="Extract speaker counts via LLM")
    extract_parser.add_argument("--meeting-date", help="Single date (YYYY-MM-DD)")
    extract_parser.add_argument("--dry-run", action="store_true", help="Preview without DB writes")
    extract_parser.add_argument("--limit", type=int, help="Limit number of meetings")

    # Run (full pipeline)
    run_parser = subparsers.add_parser("run", help="Full pipeline: fetch + extract")
    run_parser.add_argument("--meeting-date", help="Single date (YYYY-MM-DD)")
    run_parser.add_argument("--dry-run", action="store_true", help="Preview without DB writes")
    run_parser.add_argument("--limit", type=int, help="Limit number of meetings")

    args = parser.parse_args()

    if args.command == "discover":
        cmd_discover()
    elif args.command == "fetch":
        cmd_fetch(args.meeting_date)
    elif args.command == "extract":
        cmd_extract(args.meeting_date, dry_run=args.dry_run, limit=args.limit)
    elif args.command == "run":
        cmd_run(args.meeting_date, dry_run=args.dry_run, limit=args.limit)


if __name__ == "__main__":
    main()
