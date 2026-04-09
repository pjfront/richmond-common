"""
S24: Post-meeting recap orchestrator.

Combines YouTube transcript fetch, speaker count extraction, agenda-based
recap generation, and transcript-based recap generation into one workflow.
Designed to run locally (home IP bypasses YouTube's cloud-IP blocking) or
in CI with a proxy (YOUTUBE_PROXY env var).

Pipeline:
  1. Fetch transcript from KCRT YouTube (yt-dlp)
  2. Extract per-item speaker counts (Claude API)
  3. Generate agenda-based recap (meetings.meeting_recap)
  4. Generate transcript-based recap (meetings.transcript_recap)

Usage:
  python post_meeting_recap.py --meeting-date 2026-04-07
  python post_meeting_recap.py --meeting-date 2026-04-07 --dry-run
  python post_meeting_recap.py --meeting-date 2026-04-07 --skip-transcript
  python post_meeting_recap.py --meeting-date 2026-04-07 --only-transcript-recap
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

# ── Config ────────────────────────────────────────────────────────

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS_TRANSCRIPT_RECAP = 2000
PROMPTS_DIR = Path(__file__).parent / "prompts"
TRANSCRIPT_DIR = Path(__file__).parent.parent / "data" / "transcripts"


def _load_prompt(filename: str) -> str:
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text().strip()


# ── Step 1+2: Transcript fetch + speaker extraction ──────────────


def run_transcript_pipeline(
    meeting_date: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Fetch YouTube transcript and extract speaker counts.

    Returns stats dict with transcript_path, speaker_counts, etc.
    """
    from youtube_comments import (
        discover_videos,
        match_videos_to_meetings,
        fetch_transcript,
        extract_speakers,
        import_speaker_counts,
        TRANSCRIPT_DIR as YT_TRANSCRIPT_DIR,
    )

    result: dict[str, Any] = {
        "transcript_fetched": False,
        "transcript_path": None,
        "speakers_extracted": False,
        "speaker_stats": None,
    }

    # Check if transcript already exists
    clean_path = YT_TRANSCRIPT_DIR / f"{meeting_date}_clean.txt"
    if clean_path.exists():
        print(f"  Transcript already exists: {clean_path.name}")
        result["transcript_fetched"] = True
        result["transcript_path"] = clean_path
    else:
        # Discover and fetch
        print("  Discovering KCRT videos...")
        videos = discover_videos()
        matched = match_videos_to_meetings(videos)
        matched = [m for m in matched if m["meeting_date"] == meeting_date]

        if not matched:
            print(f"  No KCRT video found for {meeting_date}")
            return result

        m = matched[0]
        print(f"  Fetching transcript for {m['video_id']}...")
        path = fetch_transcript(
            m["video_id"], meeting_date,
            alt_video_ids=m.get("alt_video_ids", []),
        )
        if path:
            result["transcript_fetched"] = True
            result["transcript_path"] = path
        else:
            print(f"  Failed to fetch transcript")
            return result

    # Extract speaker counts
    clean_path = result["transcript_path"]
    meeting_id = _get_meeting_id(meeting_date)
    if not meeting_id:
        print(f"  No meeting found in DB for {meeting_date}")
        return result

    print(f"\n  Extracting speaker counts...")
    speakers = extract_speakers(clean_path, meeting_id, meeting_date)
    if speakers:
        result["speakers_extracted"] = True
        stats = import_speaker_counts(
            speakers, meeting_id, meeting_date, dry_run=dry_run,
        )
        result["speaker_stats"] = stats

        # Save raw result
        result_path = YT_TRANSCRIPT_DIR / f"{meeting_date}_result.json"
        result_path.write_text(json.dumps(speakers, indent=2))

    return result


# ── Step 3: Agenda-based recap ───────────────────────────────────


def run_agenda_recap(
    meeting_date: str,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> bool:
    """Generate agenda-based recap (meetings.meeting_recap).

    Returns True if recap was generated.
    """
    from generate_meeting_recaps import generate_recaps
    from db import get_connection

    meeting_id = _get_meeting_id(meeting_date)
    if not meeting_id:
        print(f"  No meeting found in DB for {meeting_date}")
        return False

    # Check if already generated
    if not force:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT meeting_recap IS NOT NULL FROM meetings WHERE id = %s",
                (meeting_id,),
            )
            row = cur.fetchone()
            if row and row[0]:
                print(f"  Agenda recap already exists (use --force to regenerate)")
                conn.close()
                return True
        conn.close()

    if dry_run:
        print(f"  [DRY RUN] Would generate agenda recap for {meeting_date}")
        return False

    print(f"  Generating agenda-based recap...")
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        stats = generate_recaps(conn, meeting_id=meeting_id, force=force)
        return stats["generated"] > 0
    finally:
        conn.close()


# ── Step 4: Transcript-based recap ───────────────────────────────


def generate_transcript_recap(
    meeting_date: str,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> str | None:
    """Generate recap from YouTube transcript.

    Sends the full transcript to Claude API with a transcript-specific
    system prompt. Saves to meetings.transcript_recap.

    Returns the recap text, or None on failure.
    """
    import anthropic

    meeting_id = _get_meeting_id(meeting_date)
    if not meeting_id:
        print(f"  No meeting found in DB for {meeting_date}")
        return None

    # Check if already generated
    if not force:
        from db import get_connection
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT transcript_recap IS NOT NULL FROM meetings WHERE id = %s",
                (meeting_id,),
            )
            row = cur.fetchone()
            if row and row[0]:
                print(f"  Transcript recap already exists (use --force to regenerate)")
                conn.close()
                return None
        conn.close()

    # Load transcript
    clean_path = TRANSCRIPT_DIR / f"{meeting_date}_clean.txt"
    if not clean_path.exists():
        print(f"  No transcript file for {meeting_date}")
        return None

    transcript = clean_path.read_text(encoding="utf-8")
    est_tokens = len(transcript) // 4
    print(f"  Transcript: {len(transcript):,} chars (~{est_tokens:,} tokens)")

    if dry_run:
        print(f"  [DRY RUN] Would send {est_tokens:,} tokens to Claude API")
        return None

    # Generate recap via Claude API
    system_prompt = _load_prompt("transcript_recap_system.txt")

    print(f"  Sending transcript to Claude API...")
    client = anthropic.Anthropic(timeout=120.0)
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS_TRANSCRIPT_RECAP,
        system=system_prompt,
        messages=[{
            "role": "user",
            "content": f"Write a post-meeting recap from this transcript of the "
                       f"Richmond City Council meeting on {meeting_date}:\n\n"
                       f"{transcript}",
        }],
    )

    cost = (
        response.usage.input_tokens * 0.003 / 1000
        + response.usage.output_tokens * 0.015 / 1000
    )
    print(
        f"  API: {response.usage.input_tokens:,} in / "
        f"{response.usage.output_tokens:,} out (${cost:.3f})"
    )

    # Parse JSON response
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    try:
        data = json.loads(text)
        recap = (data.get("transcript_recap") or "").strip()
    except json.JSONDecodeError:
        # Try regex extraction
        match = re.search(r'"transcript_recap"\s*:\s*"(.*)"', text, re.DOTALL)
        if match:
            recap = match.group(1).replace("\\n", "\n").strip()
        else:
            print(f"  WARNING: Could not parse JSON, using raw text")
            recap = text

    if not recap:
        print(f"  No recap content generated")
        return None

    # Save to database
    print(f"  Saving transcript recap ({len(recap)} chars)...")
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE meetings
                   SET transcript_recap = %s,
                       transcript_recap_source = 'youtube',
                       transcript_recap_generated_at = NOW()
                   WHERE id = %s""",
                (recap, meeting_id),
            )
        conn.commit()
    finally:
        conn.close()

    return recap


# ── Helpers ──────────────────────────────────────────────────────


def _get_meeting_id(meeting_date: str) -> str | None:
    """Look up meeting UUID by date."""
    from db import get_connection, RICHMOND_FIPS

    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM meetings WHERE city_fips = %s AND meeting_date = %s "
            "AND meeting_type = 'regular' LIMIT 1",
            (RICHMOND_FIPS, meeting_date),
        )
        row = cur.fetchone()
    conn.close()
    return row[0] if row else None


# ── CLI ──────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Post-meeting recap pipeline: transcript + agenda + transcript recap"
    )
    parser.add_argument(
        "--meeting-date", required=True,
        help="Meeting date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview without DB writes or API calls",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Regenerate existing recaps",
    )
    parser.add_argument(
        "--skip-transcript", action="store_true",
        help="Skip YouTube transcript fetch + speaker extraction",
    )
    parser.add_argument(
        "--skip-agenda-recap", action="store_true",
        help="Skip agenda-based recap generation",
    )
    parser.add_argument(
        "--only-transcript-recap", action="store_true",
        help="Only generate transcript-based recap (skip steps 1-3)",
    )

    args = parser.parse_args()
    date = args.meeting_date

    print(f"Post-meeting recap pipeline for {date}")
    print("=" * 50)

    skip_transcript = args.skip_transcript or args.only_transcript_recap
    skip_agenda = args.skip_agenda_recap or args.only_transcript_recap

    # Step 1+2: Transcript fetch + speaker extraction
    if not skip_transcript:
        print(f"\n[1/4] YouTube transcript + speaker counts")
        result = run_transcript_pipeline(date, dry_run=args.dry_run)
        if result["transcript_fetched"]:
            print(f"  Transcript: OK")
        else:
            print(f"  Transcript: FAILED (continuing without it)")
        if result["speakers_extracted"]:
            stats = result["speaker_stats"] or {}
            print(f"  Speakers: {stats.get('updated', 0)} items updated, "
                  f"{stats.get('open_forum', 0)} open forum")
    else:
        print(f"\n[1/4] Transcript fetch — skipped")

    # Step 3: Agenda-based recap
    if not skip_agenda:
        print(f"\n[2/4] Agenda-based recap")
        ok = run_agenda_recap(date, dry_run=args.dry_run, force=args.force)
        print(f"  {'OK' if ok else 'No recap generated'}")
    else:
        print(f"\n[2/4] Agenda recap — skipped")

    # Step 4: Transcript-based recap
    print(f"\n[3/4] Transcript-based recap")
    recap = generate_transcript_recap(date, dry_run=args.dry_run, force=args.force)
    if recap:
        print(f"  OK ({len(recap)} chars)")
        # Print first ~500 chars as preview
        print(f"\n  Preview:")
        for line in recap[:500].split("\n"):
            print(f"    {line}")
        if len(recap) > 500:
            print(f"    ...")
    else:
        print(f"  No transcript recap generated")

    print(f"\n[4/4] Done.")
    print("=" * 50)

    # Summary
    meeting_id = _get_meeting_id(date)
    if meeting_id:
        import psycopg2
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        with conn.cursor() as cur:
            cur.execute(
                "SELECT meeting_recap IS NOT NULL, transcript_recap IS NOT NULL "
                "FROM meetings WHERE id = %s",
                (meeting_id,),
            )
            row = cur.fetchone()
            has_agenda = row[0] if row else False
            has_transcript = row[1] if row else False
        conn.close()
        print(f"  Agenda recap:     {'yes' if has_agenda else 'no'}")
        print(f"  Transcript recap: {'yes' if has_transcript else 'no'}")


if __name__ == "__main__":
    main()
