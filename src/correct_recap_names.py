"""
Correct phonetic name misspellings in already-generated recap text.

Auto-generated YouTube/Granicus captions misspell names phonetically
("Gioia" → "Joya", "Aleshire" → "Alshshire"). When the recap was
generated before canonical_names.md was wired into the prompt, those
misspellings ended up in production.

This script does a single Claude pass over existing recap text using
canonical_names.md as authority. Cheap (~$0.05 per recap), works
without YouTube cookies, preserves all non-name text exactly.

Usage:
  python correct_recap_names.py --meeting-date 2026-04-21
  python correct_recap_names.py --meeting-date 2026-04-21 --dry-run
  python correct_recap_names.py --all                    # all meetings with transcript_recap
  python correct_recap_names.py --all --dry-run

Cost: ~$0.05 per recap (mostly the input tokens for canonical_names.md
+ recap text; output is small).
"""
from __future__ import annotations

from llm_client import LLMClient, ROUTINE_MODEL

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

# Windows console (cp1252) can't encode unicode arrows. Match pipeline_map.py.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

PROMPTS_DIR = Path(__file__).parent / "prompts"
RICHMOND_FIPS = "0660620"


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8").strip()


def _load_canonical_names() -> str:
    path = PROMPTS_DIR / "canonical_names.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _parse_corrected(text: str) -> str | None:
    """Parse the JSON response from Claude, extract corrected_recap."""
    try:
        data = json.loads(text)
        return (data.get("corrected_recap") or "").strip() or None
    except json.JSONDecodeError:
        # Fallback: regex-extract for lightly-malformed JSON (e.g., trailing prose)
        if '"corrected_recap"' in text:
            match = re.search(
                r'"corrected_recap"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL,
            )
            if match:
                # Unescape JSON string
                raw = match.group(1)
                return raw.encode().decode("unicode_escape")
        return None


def correct_recap(original: str) -> tuple[str | None, dict]:
    """Send recap to Claude with canonical names; return (corrected_text, stats).

    Returns (None, stats) on failure. stats includes input/output tokens.
    """
    system_prompt = _load_prompt("name_correction_system.txt")
    canonical = _load_canonical_names()
    if canonical:
        system_prompt += "\n\n---\n\nCANONICAL NAMES\n\n" + canonical

    user_prompt = (
        "Correct any phonetic name misspellings in this recap, "
        "preserving everything else exactly:\n\n" + original
    )

    client = LLMClient(timeout=60.0)
    response = client.messages.create(
        model=ROUTINE_MODEL,
        max_tokens=4000,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    corrected = _parse_corrected(response.content[0].text)
    stats = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        # Sonnet pricing as of 2025-09: $3/M in, $15/M out
        "approx_cost": (
            response.usage.input_tokens * 3 / 1_000_000
            + response.usage.output_tokens * 15 / 1_000_000
        ),
    }
    return corrected, stats


def _diff_changes(before: str, after: str) -> list[str]:
    """Return human-readable list of name changes between before and after.

    Walks word boundaries, finds tokens that differ. Best-effort — used
    for operator visibility, not strict correctness.
    """
    if before == after:
        return []
    # Cheap proxy: find words in `before` not in `after`
    before_words = set(re.findall(r"\b[A-Z][a-zA-Z'-]+\b", before))
    after_words = set(re.findall(r"\b[A-Z][a-zA-Z'-]+\b", after))
    removed = sorted(before_words - after_words)
    added = sorted(after_words - before_words)
    if not removed and not added:
        return []
    pairs = []
    # Try to pair removed → added by length-similarity heuristic (very rough)
    used = set()
    for r in removed:
        # Find best add candidate: shortest edit distance proxy = similar length
        best = None
        for a in added:
            if a in used:
                continue
            if abs(len(a) - len(r)) <= max(2, len(r) // 3):
                best = a
                break
        if best:
            pairs.append(f"{r} -> {best}")
            used.add(best)
        else:
            pairs.append(f"removed: {r}")
    for a in added:
        if a not in used:
            pairs.append(f"added: {a}")
    return pairs


def correct_meeting(meeting_date: str, dry_run: bool = False) -> dict:
    """Correct the transcript_recap for a single meeting date.

    Returns dict with status, changes, cost.
    """
    sys.path.insert(0, str(Path(__file__).parent))
    from db import get_connection

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, transcript_recap FROM meetings
                   WHERE city_fips = %s AND meeting_date = %s
                     AND meeting_type = 'regular'
                     AND transcript_recap IS NOT NULL
                """,
                (RICHMOND_FIPS, meeting_date),
            )
            row = cur.fetchone()
            if not row:
                return {"status": "no_recap", "meeting_date": meeting_date}
            meeting_id, original = row

        print(f"  Correcting {meeting_date} ({len(original)} chars)...")
        corrected, stats = correct_recap(original)
        if not corrected:
            return {"status": "parse_failed", "meeting_date": meeting_date}

        if corrected == original:
            print(f"    No changes needed (cost ${stats['approx_cost']:.4f})")
            return {"status": "no_changes", "meeting_date": meeting_date, **stats}

        changes = _diff_changes(original, corrected)
        for c in changes:
            print(f"    {c}")
        print(f"    Cost: ${stats['approx_cost']:.4f}")

        if dry_run:
            print(f"    [dry-run, not writing]")
            return {
                "status": "dry_run", "meeting_date": meeting_date,
                "changes": changes, **stats,
            }

        with conn.cursor() as cur:
            cur.execute(
                """UPDATE meetings
                   SET transcript_recap = %s,
                       transcript_recap_corrected_at = NOW()
                   WHERE id = %s
                """,
                (corrected, meeting_id),
            )
        conn.commit()
        return {
            "status": "corrected", "meeting_date": meeting_date,
            "changes": changes, **stats,
        }
    finally:
        conn.close()


def correct_all(dry_run: bool = False) -> list[dict]:
    """Correct every meeting that has a transcript_recap."""
    sys.path.insert(0, str(Path(__file__).parent))
    from db import get_connection

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT meeting_date::text FROM meetings
                   WHERE city_fips = %s AND meeting_type = 'regular'
                     AND transcript_recap IS NOT NULL
                   ORDER BY meeting_date DESC
                """,
                (RICHMOND_FIPS,),
            )
            dates = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    print(f"Found {len(dates)} meetings with transcript_recap")
    return [correct_meeting(d, dry_run=dry_run) for d in dates]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meeting-date", help="YYYY-MM-DD")
    parser.add_argument("--all", action="store_true",
                        help="Correct every meeting with a transcript_recap")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show changes without writing to DB")
    args = parser.parse_args()

    if not args.meeting_date and not args.all:
        parser.error("--meeting-date or --all required")

    if args.all:
        results = correct_all(dry_run=args.dry_run)
        total_cost = sum(r.get("approx_cost", 0) for r in results)
        n_corrected = sum(1 for r in results if r["status"] == "corrected")
        n_unchanged = sum(1 for r in results if r["status"] == "no_changes")
        print(f"\n{n_corrected} corrected, {n_unchanged} unchanged. "
              f"Total cost: ${total_cost:.4f}")
    else:
        result = correct_meeting(args.meeting_date, dry_run=args.dry_run)
        print(f"\nResult: {result['status']}")


if __name__ == "__main__":
    main()
