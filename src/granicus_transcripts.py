"""
S20: Granicus transcript pipeline for public comment speaker counts.

Granicus hosts official meeting recordings with speech-to-text transcripts
in VTT-in-PDF format. 928 meetings back to 2012, 82+ with transcripts.
Better quality than YouTube auto-captions.

URL pattern:
  Listing:    richmond.granicus.com/ViewPublisher.php?view_id=30
  Transcript: richmond.granicus.com/MinutesViewer.php?view_id=30&clip_id=N&doc_id=UUID
    -> redirects to Google Docs wrapper
    -> actual PDF: richmond.granicus.com/DocumentViewer.php?file=richmond_{hash}.pdf

Usage:
  python granicus_transcripts.py discover              # List meetings with transcripts
  python granicus_transcripts.py fetch                 # Download all transcript PDFs
  python granicus_transcripts.py fetch --meeting-date 2026-03-03
  python granicus_transcripts.py extract               # Count speakers via LLM
  python granicus_transcripts.py extract --dry-run
  python granicus_transcripts.py run                   # Full pipeline
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # type: ignore[assignment]

from db import get_connection, RICHMOND_FIPS  # noqa: E402

# -- Constants ------------------------------------------------

GRANICUS_BASE = "https://richmond.granicus.com"
GRANICUS_LISTING = f"{GRANICUS_BASE}/ViewPublisher.php?view_id=30"
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 4000

DATA_DIR = Path(__file__).parent.parent / "data"
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
PROMPT_PATH = Path(__file__).parent / "prompts" / "youtube_comments_system.txt"


def _ensure_dirs() -> None:
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)


# -- Discover -------------------------------------------------


def discover_granicus_meetings() -> list[dict[str, Any]]:
    """Scrape Granicus listing page for meetings with transcript links.

    Returns list of {clip_id, meeting_date (YYYY-MM-DD), doc_id, pdf_url}.
    """
    resp = requests.get(GRANICUS_LISTING, timeout=30)
    html = resp.text

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL)

    meetings: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in rows:
        clip_match = re.search(r"clip_id=(\d+)", row)
        if not clip_match:
            continue
        clip_id = clip_match.group(1)
        if clip_id in seen:
            continue
        seen.add(clip_id)

        date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", row)
        if not date_match:
            continue
        parts = date_match.group(1).split("/")
        meeting_date = f"{parts[2]}-{int(parts[0]):02d}-{int(parts[1]):02d}"

        doc_match = re.search(r"MinutesViewer.*?doc_id=([^\"&]+)", row)
        if not doc_match:
            continue

        meetings.append({
            "clip_id": clip_id,
            "meeting_date": meeting_date,
            "doc_id": doc_match.group(1),
        })

    return meetings


def _resolve_pdf_url(clip_id: str, doc_id: str) -> str | None:
    """Follow MinutesViewer redirect to get direct PDF URL."""
    url = f"{GRANICUS_BASE}/MinutesViewer.php?view_id=30&clip_id={clip_id}&doc_id={doc_id}"
    try:
        resp = requests.head(url, allow_redirects=True, timeout=10)
        pdf_match = re.search(r"url=([^&]+)", resp.url)
        if pdf_match:
            return unquote(pdf_match.group(1))
    except Exception:
        pass
    return None


def match_to_db_meetings(
    meetings: list[dict[str, Any]],
    city_fips: str = RICHMOND_FIPS,
) -> list[dict[str, Any]]:
    """Match Granicus meetings to database meetings by date."""
    conn = get_connection()
    matched: list[dict[str, Any]] = []

    with conn.cursor() as cur:
        for m in meetings:
            cur.execute(
                """SELECT m.id,
                          (SELECT COUNT(*) FROM agenda_items ai WHERE ai.meeting_id = m.id) as item_count
                   FROM meetings m
                   WHERE m.city_fips = %s AND m.meeting_date = %s
                   LIMIT 1""",
                (city_fips, m["meeting_date"]),
            )
            row = cur.fetchone()
            if row and row[1] > 0:  # skip meetings with 0 items
                matched.append({
                    **m,
                    "meeting_id": row[0],
                    "item_count": row[1],
                })

    conn.close()
    return matched


# -- Fetch ----------------------------------------------------


def _pdf_to_clean_text(pdf_path: Path) -> str:
    """Extract VTT text from Granicus transcript PDF.

    Granicus transcripts are VTT (WebVTT) content rendered as a PDF.
    Each page has numbered cues with timestamps and text.
    """
    if fitz is None:
        print("  ERROR: PyMuPDF required. Run: pip install PyMuPDF")
        return ""

    doc = fitz.open(str(pdf_path))
    all_text = []
    for page in doc:
        all_text.append(page.get_text())
    doc.close()

    raw = "\n".join(all_text)

    # Parse VTT cues from the PDF text
    # Format: "N\nHH:MM:SS.mmm --> HH:MM:SS.mmm\nText lines\n"
    cues: list[tuple[float, str]] = []
    cue_pattern = re.compile(
        r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}\s*\n(.*?)(?=\n\d+\s*\n\d{2}:\d{2}|\Z)",
        re.DOTALL,
    )

    for match in cue_pattern.finditer(raw):
        ts_str = match.group(1)
        text = match.group(2).strip()
        if not text:
            continue

        # Parse timestamp
        parts = ts_str.split(":")
        h, m = int(parts[0]), int(parts[1])
        s = float(parts[2])
        ts = h * 3600 + m * 60 + s

        # Clean text
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            cues.append((ts, text))

    # Format with timestamps every ~60 seconds
    output: list[str] = []
    last_ts = -60.0
    for ts, text in cues:
        if ts - last_ts >= 60:
            h = int(ts // 3600)
            m_val = int((ts % 3600) // 60)
            s_val = int(ts % 60)
            output.append(f"\n[{h}:{m_val:02d}:{s_val:02d}]")
            last_ts = ts
        output.append(text)

    return "\n".join(output)


def fetch_transcript(
    clip_id: str,
    doc_id: str,
    meeting_date: str,
) -> Path | None:
    """Download Granicus transcript PDF and convert to clean text.

    Returns path to clean text file, or None on failure.
    """
    _ensure_dirs()

    clean_path = TRANSCRIPT_DIR / f"{meeting_date}_clean.txt"
    pdf_path = TRANSCRIPT_DIR / f"{meeting_date}_granicus.pdf"

    # Skip if already fetched
    if clean_path.exists():
        print(f"  Transcript already exists: {clean_path.name}")
        return clean_path

    # Resolve PDF URL
    print(f"  Resolving PDF URL for {meeting_date} (clip {clip_id})...")
    pdf_url = _resolve_pdf_url(clip_id, doc_id)
    if not pdf_url:
        print(f"  ERROR: Could not resolve PDF URL")
        return None

    # Download PDF
    print(f"  Downloading transcript PDF...")
    try:
        resp = requests.get(pdf_url, timeout=60)
        resp.raise_for_status()
        pdf_path.write_bytes(resp.content)
        print(f"  PDF: {len(resp.content):,} bytes")
    except Exception as e:
        print(f"  ERROR: Download failed: {e}")
        return None

    # Convert to clean text
    print(f"  Extracting text from PDF...")
    clean_text = _pdf_to_clean_text(pdf_path)
    if not clean_text:
        print(f"  ERROR: No text extracted from PDF")
        return None

    clean_path.write_text(clean_text, encoding="utf-8")
    chars = len(clean_text)
    print(f"  Clean transcript: {chars:,} chars (~{chars // 4:,} tokens)")

    return clean_path


# -- Extract (reuse from youtube_comments) --------------------


def _load_system_prompt() -> str:
    """Load the system prompt for comment extraction."""
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding="utf-8").strip()
    return "You are analyzing a city council meeting transcript to count public comment speakers per agenda item. Return valid JSON only."


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
    """Get mapping of item_number -> agenda_item UUID."""
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
    """Send transcript to Claude API and extract speaker counts."""
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
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as e:
        print(f"  ERROR: API call failed: {e}")
        return None

    text = response.content[0].text
    cost = response.usage.input_tokens * 0.003 / 1000 + response.usage.output_tokens * 0.015 / 1000
    print(f"  API: {response.usage.input_tokens:,} in / {response.usage.output_tokens:,} out (${cost:.3f})")

    # Parse JSON
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  ERROR: JSON parse failed: {e}")
        print(f"  Raw: {text[:300]}")
        return None


def _normalize_item_num(s: str) -> str:
    """Normalize item number for fuzzy matching."""
    s = s.strip().upper()
    s = re.sub(r"([A-Z])(\d)", r"\1.\2", s)
    s = re.sub(r"(\d)([A-Z])", r"\1.\2", s)
    return s.lower()


def import_speaker_counts(
    result: dict[str, Any],
    meeting_id: str,
    meeting_date: str,
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    """Write speaker counts to agenda_items.public_comment_count."""
    item_id_map = _get_agenda_item_ids(meeting_id)
    norm_map = {_normalize_item_num(k): v for k, v in item_id_map.items()}
    stats = {"updated": 0, "not_found": 0, "open_forum": 0}

    items = result.get("items", [])
    open_forum = result.get("open_forum", {})

    if open_forum.get("speaker_count", 0) > 0:
        stats["open_forum"] = open_forum["speaker_count"]

    print(f"\n  {meeting_date}: {len(items)} items with comments, {stats['open_forum']} open forum")

    conn = None
    if not dry_run:
        conn = get_connection()

    for item in items:
        item_number = item.get("item_number", "")
        count = item.get("speaker_count", 0)
        methods = item.get("methods", [])
        if count == 0:
            continue

        agenda_item_id = item_id_map.get(item_number) or norm_map.get(_normalize_item_num(item_number))
        if not agenda_item_id:
            print(f"    SKIP {item_number}: {count} speakers -- not found in DB")
            stats["not_found"] += 1
            continue

        method_str = ", ".join(methods)
        print(f"    {item_number}: {count} speakers ({method_str})")

        if conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE agenda_items SET public_comment_count = %s WHERE id = %s",
                    (count, agenda_item_id),
                )
            stats["updated"] += 1

    if conn:
        conn.commit()
        conn.close()

    return stats


# -- Pipeline Commands ----------------------------------------


def cmd_discover() -> None:
    """List Granicus meetings with transcripts."""
    print("Fetching Granicus meeting archive...\n")
    meetings = discover_granicus_meetings()
    matched = match_to_db_meetings(meetings)

    print(f"Found {len(meetings)} meetings with transcripts, {len(matched)} matched to DB:\n")
    for m in sorted(matched, key=lambda x: x["meeting_date"], reverse=True)[:30]:
        print(f"  {m['meeting_date']}  {m['item_count']:3d} items  clip={m['clip_id']}")

    unmatched_count = len(meetings) - len(matched)
    if unmatched_count:
        print(f"\n  {unmatched_count} meetings not matched (no DB record or 0 items)")


def cmd_fetch(meeting_date: str | None = None) -> None:
    """Download transcript PDFs."""
    meetings = discover_granicus_meetings()
    matched = match_to_db_meetings(meetings)

    if meeting_date:
        matched = [m for m in matched if m["meeting_date"] == meeting_date]
        if not matched:
            print(f"No Granicus transcript found for {meeting_date}")
            sys.exit(1)

    print(f"Fetching transcripts for {len(matched)} meetings...\n")
    ok = fail = 0
    for m in sorted(matched, key=lambda x: x["meeting_date"], reverse=True):
        result = fetch_transcript(m["clip_id"], m["doc_id"], m["meeting_date"])
        if result:
            print(f"  OK {m['meeting_date']}")
            ok += 1
        else:
            print(f"  FAIL {m['meeting_date']}")
            fail += 1

    print(f"\nFetched: {ok} OK, {fail} failed")


def cmd_extract(
    meeting_date: str | None = None,
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> None:
    """Extract speaker counts from transcripts."""
    # Use local transcripts, matched to DB meetings
    meetings = discover_granicus_meetings()
    matched = match_to_db_meetings(meetings)

    if meeting_date:
        matched = [m for m in matched if m["meeting_date"] == meeting_date]
        if not matched:
            print(f"No meeting found for {meeting_date}")
            sys.exit(1)

    # Only process meetings that have local transcripts
    matched = [
        m for m in matched
        if (TRANSCRIPT_DIR / f"{m['meeting_date']}_clean.txt").exists()
    ]

    if limit:
        matched = sorted(matched, key=lambda x: x["meeting_date"], reverse=True)[:limit]

    total_updated = 0
    total_cost = 0.0

    tag = "[DRY RUN] " if dry_run else ""
    print(f"{tag}Extracting speaker counts for {len(matched)} meetings...\n")

    for m in sorted(matched, key=lambda x: x["meeting_date"], reverse=True):
        date = m["meeting_date"]
        clean_path = TRANSCRIPT_DIR / f"{date}_clean.txt"
        result_path = TRANSCRIPT_DIR / f"{date}_result.json"

        # Skip if already extracted (unless dry-run for re-checking)
        if result_path.exists() and not dry_run:
            print(f"\n-- {date} -- already extracted, skipping")
            # Still import existing results
            result = json.loads(result_path.read_text(encoding="utf-8"))
            stats = import_speaker_counts(result, m["meeting_id"], date, dry_run=dry_run)
            total_updated += stats["updated"]
            continue

        print(f"\n-- {date} ({m['item_count']} items) --")

        result = extract_speakers(clean_path, m["meeting_id"], date)
        if not result:
            continue

        # Save raw result
        result_path = TRANSCRIPT_DIR / f"{date}_result.json"
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        stats = import_speaker_counts(result, m["meeting_id"], date, dry_run=dry_run)
        total_updated += stats["updated"]

    print(f"\n{'=' * 50}")
    print(f"{tag}Complete: {total_updated} items updated")


def cmd_run(
    meeting_date: str | None = None,
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> None:
    """Full pipeline: fetch + extract."""
    cmd_fetch(meeting_date)
    print("\n" + "=" * 50 + "\n")
    cmd_extract(meeting_date, dry_run=dry_run, limit=limit)


# -- CLI ------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Granicus transcript pipeline for public comment counts"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("discover", help="List meetings with transcripts")

    fetch_p = subparsers.add_parser("fetch", help="Download transcript PDFs")
    fetch_p.add_argument("--meeting-date", help="Single date (YYYY-MM-DD)")

    extract_p = subparsers.add_parser("extract", help="Extract speaker counts")
    extract_p.add_argument("--meeting-date", help="Single date (YYYY-MM-DD)")
    extract_p.add_argument("--dry-run", action="store_true")
    extract_p.add_argument("--limit", type=int)

    run_p = subparsers.add_parser("run", help="Full pipeline: fetch + extract")
    run_p.add_argument("--meeting-date", help="Single date (YYYY-MM-DD)")
    run_p.add_argument("--dry-run", action="store_true")
    run_p.add_argument("--limit", type=int)

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
