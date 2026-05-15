"""
Per-agenda-item transcript windowing.

Reads from `data/transcripts/{meeting_date}_clean.txt` (raw auto-captioned
transcript — the source-closest persisted artifact). Does NOT read from
`meetings.transcript_recap` or any other derivative summary.

A single Claude pass produces per-item start/end timestamp markers; Python
deterministically slices the raw transcript on those markers and writes
`data/transcripts/{meeting_date}_windows.json` with the per-item content.

This is the unblocker for the structured 5-field vote_explainer
rebuild: the existing generator sees only the motion text + agenda metadata
and so can't surface a dissenter's stated reasoning. With per-item windows,
the explainer can read just the discussion segment for the item it's
explaining.

Cost: ~$0.20–0.30 per meeting (~60K input tokens for a 4-hour meeting +
small JSON output of just markers).

Usage:
  python window_meeting_transcript.py --meeting-date 2026-03-17
  python window_meeting_transcript.py --meeting-date 2026-03-17 --dry-run
  python window_meeting_transcript.py --all
  python window_meeting_transcript.py --all --skip-existing  # default
"""
from __future__ import annotations

import anthropic_budget_lock  # noqa: F401  # must import before anthropic SDK

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

PROMPTS_DIR = Path(__file__).parent / "prompts"
TRANSCRIPTS_DIR = Path(__file__).parent.parent / "data" / "transcripts"
RICHMOND_FIPS = "0660620"

TIMESTAMP_RE = re.compile(r"\[\d{1,2}:\d{2}:\d{2}\]")


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8").strip()


def _load_raw_transcript(meeting_date: str) -> str | None:
    path = TRANSCRIPTS_DIR / f"{meeting_date}_clean.txt"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _parse_response(text: str) -> dict | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return None


def _slice_window(transcript: str, start_marker: str, end_marker: str) -> str | None:
    """Return the substring of `transcript` between the first occurrences
    of start_marker and end_marker (inclusive of start_marker line,
    exclusive of end_marker line). Returns None if either marker is
    missing or end is before start.
    """
    start_idx = transcript.find(start_marker)
    if start_idx < 0:
        return None
    # Search after the start marker so a model-returned end_marker that
    # appears earlier in the transcript can't silently produce a forward-
    # spanning window from the wrong place.
    end_idx = transcript.find(end_marker, start_idx + len(start_marker))
    if end_idx < 0 or end_idx <= start_idx:
        return None
    return transcript[start_idx:end_idx].rstrip()


def window_transcript(
    transcript: str,
    agenda_items: list[dict],
) -> tuple[dict | None, dict]:
    """Single Claude pass; returns (parsed_response, stats)."""
    try:
        import anthropic
    except ImportError as e:
        raise ImportError("anthropic package required. pip install anthropic") from e

    system_prompt = _load_prompt("transcript_windowing_system.txt")

    agenda_lines = [
        f"  {ai['item_number']} | {(ai.get('title') or '').strip()[:140]}"
        for ai in agenda_items
    ]

    user_prompt = (
        "Window this transcript by agenda item. Return ONLY the JSON shape "
        "in the system prompt — no commentary.\n\n"
        f"AGENDA ITEMS:\n" + "\n".join(agenda_lines) + "\n\n"
        f"TRANSCRIPT:\n{transcript}"
    )

    client = anthropic.Anthropic(timeout=180.0)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    parsed = _parse_response(response.content[0].text)

    stats = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "approx_cost": (
            response.usage.input_tokens * 3 / 1_000_000
            + response.usage.output_tokens * 15 / 1_000_000
        ),
        "model": response.model,
    }
    return parsed, stats


def _load_meeting_data(conn, meeting_date: str) -> dict | None:
    """Fetch meeting + agenda items for one date. Returns None if no
    transcript exists for the meeting (eligibility check)."""
    raw = _load_raw_transcript(meeting_date)
    if not raw:
        return None

    with conn.cursor() as cur:
        cur.execute(
            """SELECT id FROM meetings
               WHERE city_fips = %s AND meeting_date = %s
                 AND meeting_type = 'regular'
            """,
            (RICHMOND_FIPS, meeting_date),
        )
        row = cur.fetchone()
        if not row:
            return None
        meeting_id = row[0]

        cur.execute(
            """SELECT id, item_number, title FROM agenda_items
               WHERE meeting_id = %s
               ORDER BY item_number
            """,
            (meeting_id,),
        )
        agenda_items = [
            {"id": str(r[0]), "item_number": r[1], "title": r[2]}
            for r in cur.fetchall()
        ]

    return {
        "meeting_id": str(meeting_id),
        "meeting_date": meeting_date,
        "transcript_text": raw,
        "agenda_items": agenda_items,
    }


def _build_output_doc(
    meeting_date: str,
    meeting_id: str,
    transcript: str,
    agenda_items: list[dict],
    parsed: dict,
    stats: dict,
) -> dict:
    """Compose the final windows JSON: marker validation + content slicing."""
    item_by_num = {ai["item_number"]: ai for ai in agenda_items}
    windows_out: list[dict] = []
    no_match: list[dict] = []
    invalid: list[dict] = []

    for w in parsed.get("windows", []):
        item_num = w.get("agenda_item_number")
        ai = item_by_num.get(item_num) if item_num else None
        if not ai:
            invalid.append({"agenda_item_number": item_num, "reason": "unknown_item_number"})
            continue

        if w.get("status") == "no_match":
            no_match.append({
                "agenda_item_number": item_num,
                "agenda_item_id": ai["id"],
                "agenda_item_title": ai["title"],
                "note": w.get("note", ""),
            })
            continue

        start_marker = w.get("start_marker", "")
        end_marker = w.get("end_marker", "")
        if not (TIMESTAMP_RE.fullmatch(start_marker) and TIMESTAMP_RE.fullmatch(end_marker)):
            invalid.append({
                "agenda_item_number": item_num,
                "reason": "marker_format_invalid",
                "start_marker": start_marker,
                "end_marker": end_marker,
            })
            continue

        text = _slice_window(transcript, start_marker, end_marker)
        if text is None:
            invalid.append({
                "agenda_item_number": item_num,
                "reason": "marker_not_found_in_transcript",
                "start_marker": start_marker,
                "end_marker": end_marker,
            })
            continue

        windows_out.append({
            "agenda_item_number": item_num,
            "agenda_item_id": ai["id"],
            "agenda_item_title": ai["title"],
            "start_marker": start_marker,
            "end_marker": end_marker,
            "boundary_evidence": w.get("boundary_evidence", ""),
            "confidence": float(w.get("confidence", 0.0)),
            "char_count": len(text),
            "transcript_text": text,
        })

    return {
        "meeting_date": meeting_date,
        "meeting_id": meeting_id,
        "windowing_model": stats.get("model"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {k: v for k, v in stats.items() if k != "model"},
        "windows": windows_out,
        "no_match_items": no_match,
        "invalid_markers": invalid,
    }


def window_meeting(
    conn,
    meeting_date: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Window one meeting; write {date}_windows.json. Returns a summary dict."""
    data = _load_meeting_data(conn, meeting_date)
    if not data:
        return {"meeting_date": meeting_date, "skipped": True, "reason": "no_transcript_or_meeting"}

    if not data["agenda_items"]:
        return {"meeting_date": meeting_date, "skipped": True, "reason": "no_agenda_items"}

    if dry_run:
        return {
            "meeting_date": meeting_date,
            "skipped": True,
            "reason": "dry_run",
            "agenda_items": len(data["agenda_items"]),
            "transcript_chars": len(data["transcript_text"]),
        }

    parsed, stats = window_transcript(data["transcript_text"], data["agenda_items"])
    if not parsed:
        return {"meeting_date": meeting_date, "error": "parse_failure", "stats": stats}

    doc = _build_output_doc(
        meeting_date=meeting_date,
        meeting_id=data["meeting_id"],
        transcript=data["transcript_text"],
        agenda_items=data["agenda_items"],
        parsed=parsed,
        stats=stats,
    )

    out_path = TRANSCRIPTS_DIR / f"{meeting_date}_windows.json"
    out_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    return {
        "meeting_date": meeting_date,
        "windows_written": len(doc["windows"]),
        "no_match": len(doc["no_match_items"]),
        "invalid": len(doc["invalid_markers"]),
        "agenda_items_total": len(data["agenda_items"]),
        "approx_cost": stats.get("approx_cost"),
        "out_path": str(out_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Per-item transcript windowing")
    parser.add_argument("--meeting-date", help="YYYY-MM-DD (single meeting)")
    parser.add_argument("--all", action="store_true", help="All meetings with raw transcripts")
    parser.add_argument("--skip-existing", action="store_true", default=True,
                        help="Skip meetings that already have a _windows.json (default)")
    parser.add_argument("--force", action="store_true",
                        help="Regenerate even if _windows.json exists")
    parser.add_argument("--dry-run", action="store_true",
                        help="Plan only; no Claude calls or writes")
    args = parser.parse_args()

    if not args.meeting_date and not args.all:
        parser.error("Provide --meeting-date or --all")

    from db import get_connection  # noqa: E402
    conn = get_connection()

    if args.meeting_date:
        dates = [args.meeting_date]
    else:
        dates = sorted({
            p.stem.replace("_clean", "")
            for p in TRANSCRIPTS_DIR.glob("*_clean.txt")
        })

    total_cost = 0.0
    for d in dates:
        out_path = TRANSCRIPTS_DIR / f"{d}_windows.json"
        if out_path.exists() and not args.force:
            print(f"[skip] {d}: _windows.json already exists (use --force to regenerate)")
            continue
        print(f"[run]  {d}: windowing transcript...")
        try:
            result = window_meeting(conn, d, dry_run=args.dry_run)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue
        if result.get("skipped"):
            print(f"  skipped: {result.get('reason')}")
        elif result.get("error"):
            print(f"  ERROR: {result['error']}")
        else:
            cost = result.get("approx_cost") or 0.0
            total_cost += cost
            print(f"  ok: {result['windows_written']} windows, "
                  f"{result['no_match']} no-match, {result['invalid']} invalid, "
                  f"${cost:.3f}, -> {result['out_path']}")

    if total_cost:
        print(f"\nTotal Claude cost: ${total_cost:.3f}")
    conn.close()


if __name__ == "__main__":
    main()
