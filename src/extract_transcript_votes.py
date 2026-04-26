"""
Extract preliminary motions + votes from transcript_recap text.

Background: official council minutes (with structured motion+vote tallies)
publish 4-6 weeks after each meeting. Until then, the per-item vote
display on the website shows "Comment details will appear once meeting
records are processed" — even though the recap text we already have
mentions vote outcomes in plain English ("rejected by a 4-3 vote, with
Brown, Bana, Robinson, Zepeda voting against").

This script does a Claude pass over the existing transcript_recap to
extract structured motion+vote records, tagged source='transcript' so
they can be visually distinguished from minutes-derived ground truth.
When minutes_extraction later inserts source='minutes' rows for the
same agenda_item, it deletes the source='transcript' rows first.

Cost: ~$0.05-0.08 per recap (recap text + agenda items + roster as
input; small JSON output).

Usage:
  python extract_transcript_votes.py --meeting-date 2026-04-21
  python extract_transcript_votes.py --meeting-date 2026-04-21 --dry-run
  python extract_transcript_votes.py --all                    # all eligible
  python extract_transcript_votes.py --all --dry-run

Eligibility: meeting has transcript_recap NOT NULL AND no source='minutes'
motions yet. Once minutes arrive, this script becomes a no-op for that
meeting.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

PROMPTS_DIR = Path(__file__).parent / "prompts"
RICHMOND_FIPS = "0660620"


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8").strip()


def _parse_response(text: str) -> dict | None:
    """Parse JSON response from Claude. Returns dict with `motions` list."""
    try:
        data = json.loads(text)
        return data
    except json.JSONDecodeError:
        # Fallback: extract JSON block if Claude wrapped it in prose
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return None


def extract_votes(
    recap: str,
    agenda_items: list[dict],
    council_members: list[dict],
) -> tuple[list[dict] | None, dict]:
    """Send recap + agenda + roster to Claude; return (motions, stats).

    Returns ([], stats) if Claude finds no extractable motions.
    Returns (None, stats) on parse failure.
    """
    try:
        import anthropic
    except ImportError as e:
        raise ImportError("anthropic package required. pip install anthropic") from e

    system_prompt = _load_prompt("transcript_vote_extraction_system.txt")

    agenda_lines = [
        f"  {ai['item_number']} | {(ai.get('title') or '').strip()[:120]}"
        for ai in agenda_items
    ]
    council_lines = [
        f"  - {m['name']} ({m.get('role') or ''}, {m.get('seat') or ''})"
        for m in council_members
    ]

    user_prompt = (
        "Extract structured motions + votes from this recap, mapping each "
        "to the appropriate agenda_item by item_number. Return JSON only.\n\n"
        f"COUNCIL MEMBERS:\n" + "\n".join(council_lines) + "\n\n"
        f"AGENDA ITEMS:\n" + "\n".join(agenda_lines) + "\n\n"
        f"RECAP:\n{recap}"
    )

    client = anthropic.Anthropic(timeout=60.0)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    parsed = _parse_response(response.content[0].text)
    motions = parsed.get("motions") if isinstance(parsed, dict) else None

    stats = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        # Sonnet pricing as of 2025-09: $3/M in, $15/M out
        "approx_cost": (
            response.usage.input_tokens * 3 / 1_000_000
            + response.usage.output_tokens * 15 / 1_000_000
        ),
    }
    return motions, stats


def _load_meeting_data(conn, meeting_date: str) -> dict | None:
    """Fetch meeting + agenda items + council roster for one date."""
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
            return None
        meeting_id, recap = row

        # Skip if minutes-sourced motions already exist (ground truth wins)
        cur.execute(
            """SELECT COUNT(*) FROM motions mo
               JOIN agenda_items ai ON ai.id = mo.agenda_item_id
               WHERE ai.meeting_id = %s AND mo.source = 'minutes'
            """,
            (meeting_id,),
        )
        if cur.fetchone()[0] > 0:
            return {"skip_reason": "minutes_already_present", "meeting_id": meeting_id}

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

        cur.execute(
            """SELECT id, name, role, seat FROM officials
               WHERE city_fips = %s AND is_current = TRUE
               ORDER BY role DESC, seat NULLS LAST
            """,
            (RICHMOND_FIPS,),
        )
        council = [
            {"id": str(r[0]), "name": r[1], "role": r[2], "seat": r[3]}
            for r in cur.fetchall()
        ]

    return {
        "meeting_id": meeting_id,
        "recap": recap,
        "agenda_items": agenda_items,
        "council": council,
    }


def _insert_motions(conn, meeting_id, agenda_items, council, motions: list[dict]) -> int:
    """Write extracted motions+votes to DB with source='transcript'.

    Returns number of motion rows inserted.
    """
    item_lookup = {ai["item_number"]: ai["id"] for ai in agenda_items}
    council_lookup = {m["name"]: (m["id"], m["role"]) for m in council}

    inserted = 0
    with conn.cursor() as cur:
        # Clear any existing transcript-sourced motions for this meeting
        # (idempotent: re-running this script regenerates rather than dups)
        cur.execute(
            """DELETE FROM motions
               WHERE source = 'transcript'
                 AND agenda_item_id IN (
                   SELECT id FROM agenda_items WHERE meeting_id = %s
                 )
            """,
            (meeting_id,),
        )

        for seq, m in enumerate(motions, start=1):
            item_num = m.get("agenda_item_number")
            agenda_item_id = item_lookup.get(item_num)
            if not agenda_item_id:
                # Couldn't match — skip rather than orphan
                print(f"    skip motion (no agenda_item match for {item_num})")
                continue

            cur.execute(
                """INSERT INTO motions
                   (agenda_item_id, motion_type, motion_text, moved_by,
                    seconded_by, result, vote_tally, sequence_number, source)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'transcript')
                   RETURNING id
                """,
                (
                    agenda_item_id,
                    "main",  # Default — recap rarely distinguishes amendment vs. main
                    m.get("motion_text") or "",
                    m.get("moved_by"),
                    m.get("seconded_by"),
                    m.get("result"),
                    m.get("vote_tally"),
                    seq,
                ),
            )
            motion_id = cur.fetchone()[0]
            inserted += 1

            for v in m.get("votes") or []:
                name = v.get("official_name")
                lookup = council_lookup.get(name)
                if not lookup:
                    print(f"    skip vote (unknown councilmember: {name})")
                    continue
                official_id, role = lookup
                cur.execute(
                    """INSERT INTO votes
                       (motion_id, official_id, official_name, official_role,
                        vote_choice, source)
                       VALUES (%s, %s, %s, %s, %s, 'transcript')
                    """,
                    (motion_id, official_id, name, role, v.get("vote_choice")),
                )

    conn.commit()
    return inserted


def extract_meeting(meeting_date: str, dry_run: bool = False) -> dict:
    """Extract transcript-sourced motions+votes for one meeting."""
    sys.path.insert(0, str(Path(__file__).parent))
    from db import get_connection

    conn = get_connection()
    try:
        data = _load_meeting_data(conn, meeting_date)
        if not data:
            return {"status": "no_recap", "meeting_date": meeting_date}
        if "skip_reason" in data:
            print(f"  Skip {meeting_date}: {data['skip_reason']}")
            return {"status": "skipped", "reason": data["skip_reason"],
                    "meeting_date": meeting_date}

        print(f"  Extracting {meeting_date} (recap {len(data['recap'])} chars, "
              f"{len(data['agenda_items'])} agenda items)...")
        motions, stats = extract_votes(
            data["recap"], data["agenda_items"], data["council"],
        )

        if motions is None:
            print(f"    Parse failed (cost ${stats['approx_cost']:.4f})")
            return {"status": "parse_failed", "meeting_date": meeting_date, **stats}

        print(f"    Found {len(motions)} motion(s); cost ${stats['approx_cost']:.4f}")
        for m in motions:
            tally = m.get("vote_tally") or "?"
            result = m.get("result") or "?"
            item = m.get("agenda_item_number") or "?"
            print(f"      [{item}] {result} {tally}: "
                  f"{(m.get('motion_text') or '')[:80]}")

        if dry_run:
            print(f"    [dry-run, not writing]")
            return {"status": "dry_run", "meeting_date": meeting_date,
                    "motion_count": len(motions), **stats}

        inserted = _insert_motions(
            conn, data["meeting_id"], data["agenda_items"],
            data["council"], motions,
        )
        return {"status": "extracted", "meeting_date": meeting_date,
                "motion_count": inserted, **stats}
    finally:
        conn.close()


def extract_all(dry_run: bool = False) -> list[dict]:
    """Run extraction for every eligible meeting."""
    sys.path.insert(0, str(Path(__file__).parent))
    from db import get_connection

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT m.meeting_date::text
                   FROM meetings m
                   WHERE m.city_fips = %s
                     AND m.meeting_type = 'regular'
                     AND m.transcript_recap IS NOT NULL
                     AND NOT EXISTS (
                       SELECT 1 FROM motions mo
                       JOIN agenda_items ai ON ai.id = mo.agenda_item_id
                       WHERE ai.meeting_id = m.id AND mo.source = 'minutes'
                     )
                   ORDER BY m.meeting_date DESC
                """,
                (RICHMOND_FIPS,),
            )
            dates = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    print(f"Found {len(dates)} eligible meeting(s) (recap present, no minutes yet)")
    return [extract_meeting(d, dry_run=dry_run) for d in dates]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meeting-date", help="YYYY-MM-DD")
    parser.add_argument("--all", action="store_true",
                        help="Extract for every eligible meeting")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show extraction without writing to DB")
    args = parser.parse_args()

    if not args.meeting_date and not args.all:
        parser.error("--meeting-date or --all required")

    if args.all:
        results = extract_all(dry_run=args.dry_run)
        n_extracted = sum(1 for r in results if r["status"] == "extracted")
        n_skipped = sum(1 for r in results if r["status"] == "skipped")
        total_motions = sum(r.get("motion_count", 0) for r in results)
        total_cost = sum(r.get("approx_cost", 0) for r in results)
        print(f"\n{n_extracted} extracted ({total_motions} motions), "
              f"{n_skipped} skipped. Total cost: ${total_cost:.4f}")
    else:
        result = extract_meeting(args.meeting_date, dry_run=args.dry_run)
        print(f"\nResult: {result['status']}")


if __name__ == "__main__":
    main()
