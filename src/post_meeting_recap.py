"""
Post-meeting orchestrator: fetch YouTube transcript and generate recap.

Single-purpose pipeline that runs after a council meeting ends:
1. Check if today is a meeting day
2. Poll YouTube for the video
3. Download auto-generated captions
4. Generate transcript recap via Claude API
5. Notify operator (or auto-send when graduated)

Designed to run every 5 min on meeting nights via GitHub Actions.
Idempotent: skips if recap already generated for today's meeting.

Usage:
    python post_meeting_recap.py --auto                     # detect tonight's meeting
    python post_meeting_recap.py --meeting-date 2026-04-07  # specific date
    python post_meeting_recap.py --dry-run                  # preview without saving
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

from db import get_connection, RICHMOND_FIPS  # noqa: E402


# ── Meeting detection ─────────────────────────────────────────


def get_meeting_for_date(
    meeting_date: str,
    city_fips: str = RICHMOND_FIPS,
) -> dict | None:
    """Check if there's a council meeting on the given date.

    Returns meeting dict {id, meeting_date, meeting_type, transcript_recap}
    or None.
    """
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT m.id, m.meeting_date, m.meeting_type, m.transcript_recap "
            "FROM meetings m "
            "WHERE m.city_fips = %s AND m.meeting_date = %s "
            "LIMIT 1",
            (city_fips, meeting_date),
        )
        row = cur.fetchone()
    conn.close()

    if not row:
        return None
    return {
        "id": str(row[0]),
        "meeting_date": str(row[1]),
        "meeting_type": row[2],
        "transcript_recap": row[3],
    }


def get_todays_meeting(city_fips: str = RICHMOND_FIPS) -> dict | None:
    """Check if there's a council meeting today."""
    today = date.today().isoformat()
    return get_meeting_for_date(today, city_fips)


# ── YouTube polling ───────────────────────────────────────────


def poll_youtube_for_meeting(meeting_date: str) -> str | None:
    """Search KCRT YouTube channel for a video matching the meeting date.

    Lightweight single-date check. Returns video_id or None.
    """
    from youtube_comments import discover_videos

    logger.info(f"Polling YouTube for {meeting_date} video...")
    videos = discover_videos()

    for video in videos:
        if video["meeting_date"] == meeting_date:
            logger.info(f"  Found: {video['title']} ({video['video_id']})")
            return video["video_id"]

    logger.info(f"  No video found for {meeting_date}")
    return None


# ── Full pipeline ─────────────────────────────────────────────


def run_post_meeting_recap(
    meeting_date: str,
    city_fips: str = RICHMOND_FIPS,
    dry_run: bool = False,
) -> dict:
    """Full pipeline: detect meeting -> fetch transcript -> generate recap.

    Returns status dict with timing breakdown.
    """
    t0 = time.time()
    result: dict = {
        "meeting_date": meeting_date,
        "status": "unknown",
        "timings": {},
    }

    # 1. Check meeting exists
    meeting = get_meeting_for_date(meeting_date, city_fips)
    if not meeting:
        result["status"] = "no_meeting"
        logger.info(f"No meeting found for {meeting_date}")
        return result

    result["meeting_id"] = meeting["id"]

    # 2. Check if recap already exists (idempotent)
    if meeting["transcript_recap"] and not dry_run:
        result["status"] = "already_generated"
        logger.info(f"Transcript recap already exists for {meeting_date}")
        return result

    # 3. Check for local transcript first
    from transcript_utils import fetch_best_transcript

    t1 = time.time()
    local = fetch_best_transcript(meeting_date)
    if local:
        transcript_text, source = local
        logger.info(
            f"Found local {source} transcript: {len(transcript_text):,} chars"
        )
    else:
        # 4. Poll YouTube for video
        video_id = poll_youtube_for_meeting(meeting_date)
        if not video_id:
            result["status"] = "no_video"
            result["timings"]["poll"] = round(time.time() - t1, 1)
            return result

        # 5. Download transcript
        from youtube_comments import fetch_transcript

        transcript_path = fetch_transcript(video_id, meeting_date)
        if not transcript_path:
            result["status"] = "no_captions"
            result["video_id"] = video_id
            result["timings"]["fetch"] = round(time.time() - t1, 1)
            return result

        transcript_text = transcript_path.read_text(encoding="utf-8")
        source = "youtube"

    result["timings"]["transcript"] = round(time.time() - t1, 1)
    result["source"] = source
    result["transcript_chars"] = len(transcript_text)

    if dry_run:
        result["status"] = "dry_run"
        logger.info(
            f"DRY RUN: Would generate recap from {source} transcript "
            f"({len(transcript_text):,} chars)"
        )
        return result

    # 6. Generate recap
    t2 = time.time()
    from generate_transcript_recaps import generate_transcript_recaps

    conn = get_connection()
    try:
        stats = generate_transcript_recaps(
            conn,
            city_fips=city_fips,
            meeting_date=meeting_date,
            source=source,
        )
    finally:
        conn.close()

    result["timings"]["generation"] = round(time.time() - t2, 1)
    result["timings"]["total"] = round(time.time() - t0, 1)

    if stats["generated"] > 0:
        result["status"] = "generated"
        logger.info(
            f"Recap generated in {result['timings']['total']:.1f}s "
            f"(transcript: {result['timings']['transcript']:.1f}s, "
            f"generation: {result['timings']['generation']:.1f}s)"
        )
    else:
        result["status"] = "generation_failed"
        result["errors"] = stats.get("errors", 0)

    return result


# ── CLI ───────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Post-meeting recap: fetch transcript and generate recap"
    )
    parser.add_argument(
        "--meeting-date",
        help="Meeting date (YYYY-MM-DD). Defaults to today with --auto.",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Detect today's meeting automatically",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without saving",
    )
    args = parser.parse_args()

    if args.auto:
        meeting_date = date.today().isoformat()
        logger.info(f"Auto mode: checking for meeting on {meeting_date}")
    elif args.meeting_date:
        meeting_date = args.meeting_date
    else:
        parser.error("Specify --meeting-date or --auto")
        return

    result = run_post_meeting_recap(meeting_date, dry_run=args.dry_run)

    print(json.dumps(result, indent=2))

    # Exit code: 0 = generated or already done, 1 = no meeting/video, 2 = error
    if result["status"] in ("generated", "already_generated", "dry_run"):
        sys.exit(0)
    elif result["status"] in ("no_meeting", "no_video", "no_captions"):
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
