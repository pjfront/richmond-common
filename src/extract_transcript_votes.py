"""
Extract preliminary motions + votes from a meeting's transcript material.

Background: official council minutes (with structured motion+vote tallies)
publish 4-6 weeks after each meeting. Until then, the per-item vote display
on the website shows "Comment details will appear once meeting records are
processed" — even though the auto-captioned recording transcribes the
roll call verbatim ("Councilmember Brown? Yes. Councilmember Bana? Yes.
Councilmember Jimenez? No.").

This script does a Claude pass over the most-source-of-truth transcript
material available, in this preference order:

  1. data/transcripts/{meeting_date}_clean.txt — the persisted raw
     auto-caption (timestamps stripped). PREFERRED. Contains the literal
     roll call text, names every speaker spoke aloud, and never omits
     substantive votes.
  2. meetings.transcript_recap (DB column) — the curated summary
     generated FROM the raw transcript. Smaller (~3KB) and cheaper to
     process, but may have summarized away substantive votes (Entry 50
     in JOURNAL.md: the 3/17 Flock 4-3 vote was missing from the recap
     entirely; only the raw transcript had the roll call).

Extracted records are tagged source='transcript' so they can be visually
distinguished from minutes-derived ground truth (see VoteRollCall.tsx
amber "Tentative" badge). When minutes_extraction later inserts
source='minutes' rows for the same agenda_item, it deletes the
source='transcript' rows first (see db.py::save_meeting_data).

Cost:
  - raw transcript input: ~$0.20-0.30 per meeting (~60K input tokens for
    a typical 4-hour meeting + small JSON output)
  - recap fallback: ~$0.05-0.08 per meeting

Usage:
  python extract_transcript_votes.py --meeting-date 2026-04-21
  python extract_transcript_votes.py --meeting-date 2026-04-21 --dry-run
  python extract_transcript_votes.py --all                    # all eligible
  python extract_transcript_votes.py --all --dry-run

Eligibility: meeting has transcript_recap NOT NULL (signals "transcript
processing has happened") AND no source='minutes' motions yet. Once
minutes arrive, this script becomes a no-op for that meeting.
"""
from __future__ import annotations

import anthropic_budget_lock  # noqa: F401  # must import before anthropic SDK

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
TRANSCRIPTS_DIR = Path(__file__).parent.parent / "data" / "transcripts"
RICHMOND_FIPS = "0660620"


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8").strip()


def _load_raw_transcript(meeting_date: str) -> str | None:
    """Return persisted raw auto-captioned transcript text, or None if absent.

    The transcript-fetch pipeline writes three artifacts per meeting:
      - {date}.en.vtt           — raw VTT with timestamps
      - {date}_clean.txt        — VTT stripped to plain text (what we want)
      - {date}_result.json      — fetch metadata

    We read the _clean.txt variant: timestamps removed, speaker labels
    preserved when present, line-broken at caption boundaries. This is
    the closest-to-source representation we keep — every roll call,
    every motion, every name spoken aloud.
    """
    path = TRANSCRIPTS_DIR / f"{meeting_date}_clean.txt"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


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
    transcript_text: str,
    agenda_items: list[dict],
    council_members: list[dict],
    transcript_source: str = "raw_transcript",
) -> tuple[list[dict] | None, dict]:
    """Send transcript material + agenda + roster to Claude.

    Args:
      transcript_text: Either the raw auto-caption (preferred) or the
        curated transcript_recap. The prompt handles both — Claude is told
        which form it's seeing so it can adjust its extraction strategy
        (raw transcripts have many procedural motions to skip; recaps
        already filter most procedural noise).
      transcript_source: "raw_transcript" or "recap" — passed to the
        prompt as a header so Claude can adjust.

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

    # Label the transcript material so Claude knows what to expect.
    # Auto-captions phonetically mishear names ("Bona" -> Bana, "Zapeda"
    # -> Zepeda); the COUNCIL MEMBERS list above provides canonical
    # spellings the prompt instructs Claude to use in output.
    if transcript_source == "raw_transcript":
        material_header = (
            "TRANSCRIPT (raw auto-caption from the meeting recording — "
            "speakers labeled when caption could identify them; expect "
            "phonetic mishearings of names which you should normalize "
            "against the COUNCIL MEMBERS list):"
        )
    else:
        material_header = (
            "TRANSCRIPT (curated summary recap — substantive votes only, "
            "may use plain English like \"4-3 vote\" rather than verbatim "
            "roll call):"
        )

    user_prompt = (
        "Extract structured motions + votes from this transcript material, "
        "mapping each to the appropriate agenda_item by item_number. Return "
        "JSON only.\n\n"
        f"COUNCIL MEMBERS:\n" + "\n".join(council_lines) + "\n\n"
        f"AGENDA ITEMS:\n" + "\n".join(agenda_lines) + "\n\n"
        f"{material_header}\n{transcript_text}"
    )

    # Larger max_tokens for raw transcripts since they tend to surface
    # more substantive motions (3/17 raw transcript: 4 motions vs 0
    # in recap).
    max_tokens = 8000 if transcript_source == "raw_transcript" else 4000

    client = anthropic.Anthropic(timeout=120.0)
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=max_tokens,
        # Deterministic extraction. With default temperature (1.0) the
        # same 3/17 transcript was returning 5, 0, and 4 motions across
        # three runs — high variance is unacceptable when the output
        # drives a vote display. Temperature=0 picks the highest-
        # probability completion every time.
        thinking={"type": "disabled"},  # Sonnet 5: sampling params removed (temperature=0 now 400s); thinking disabled keeps extraction cost/behavior closest to sonnet-4.
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
    """Fetch meeting + agenda items + council roster for one date.

    Resolves transcript material with this preference:
      1. data/transcripts/{date}_clean.txt (raw auto-caption) — preferred
      2. meetings.transcript_recap (curated summary) — fallback

    Returns dict with `transcript_text`, `transcript_source`, and
    `recap_fallback` keys, or None if the meeting is ineligible.

    The `recap_fallback` field carries the recap text whenever the raw
    transcript was selected — used by extract_meeting() to retry against
    the recap if the raw-transcript pass returns 0 motions. (Failure
    mode observed on 4/07: 354K-char raw transcript reliably returned
    {"motions": []} despite a clear unanimous roll call in the text;
    the smaller, curated recap surfaces the same vote consistently.)
    """
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

    # Prefer raw transcript over recap — Entry 50 documented the
    # failure mode where a recap omitted a substantive 4-3 vote
    # entirely. The raw transcript is the source-of-truth artifact;
    # the recap is its summary.
    raw = _load_raw_transcript(meeting_date)
    if raw:
        transcript_text = raw
        transcript_source = "raw_transcript"
        # Carry the recap as a fallback for very long transcripts
        # where the model returns 0 motions despite clear roll calls.
        recap_fallback = recap
    else:
        transcript_text = recap
        transcript_source = "recap"
        recap_fallback = None

    return {
        "meeting_id": meeting_id,
        "transcript_text": transcript_text,
        "transcript_source": transcript_source,
        "recap_fallback": recap_fallback,
        "agenda_items": agenda_items,
        "council": council,
    }


# Canonical DB values used by the existing minutes-extracted rows. Any
# transcript-extracted output that drifts ("yes" / "rejected" / etc.) gets
# mapped here at write time so downstream tally counters
# (significance.ts, VoteRollCall.computeTally) match.
_VOTE_CHOICE_CANONICAL = {
    "aye": "aye", "yes": "aye", "yea": "aye", "y": "aye",
    "nay": "nay", "no": "nay", "noe": "nay", "n": "nay",
    "abstain": "abstain", "abstained": "abstain",
    "absent": "absent",
}
_RESULT_CANONICAL = {
    "passed": "passed", "approved": "passed", "adopted": "passed",
    "failed": "failed", "rejected": "failed", "denied": "failed",
    "continued": "continued",
}


def _normalize_vote_choice(raw: str | None) -> str | None:
    if not raw:
        return None
    return _VOTE_CHOICE_CANONICAL.get(raw.strip().lower(), raw.strip().lower())


def _normalize_result(raw: str | None) -> str | None:
    if not raw:
        return None
    return _RESULT_CANONICAL.get(raw.strip().lower(), raw.strip().lower())


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
                    _normalize_result(m.get("result")),
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
                    (motion_id, official_id, name, role,
                     _normalize_vote_choice(v.get("vote_choice"))),
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

        source_label = (
            "raw transcript" if data["transcript_source"] == "raw_transcript"
            else "recap (raw transcript missing)"
        )
        print(f"  Extracting {meeting_date} ({source_label}, "
              f"{len(data['transcript_text']):,} chars, "
              f"{len(data['agenda_items'])} agenda items)...")
        motions, stats = extract_votes(
            data["transcript_text"], data["agenda_items"], data["council"],
            transcript_source=data["transcript_source"],
        )

        # Fallback: very long raw transcripts (350K+ chars) reliably
        # return {"motions": []} even when the auto-caption clearly
        # contains a roll call. When that happens, retry against the
        # curated recap, which is denser and seems to elicit better
        # extraction. Cost: a second API call (~$0.02-0.05 for the
        # smaller recap).
        if (
            motions is not None
            and len(motions) == 0
            and data["transcript_source"] == "raw_transcript"
            and data.get("recap_fallback")
        ):
            print(f"    Raw transcript yielded 0 motions; retrying against curated recap...")
            fallback_motions, fallback_stats = extract_votes(
                data["recap_fallback"], data["agenda_items"], data["council"],
                transcript_source="recap",
            )
            stats["approx_cost"] += fallback_stats["approx_cost"]
            stats["input_tokens"] += fallback_stats["input_tokens"]
            stats["output_tokens"] += fallback_stats["output_tokens"]
            if fallback_motions and len(fallback_motions) > 0:
                motions = fallback_motions
                # Mark that we used the fallback so the print log is honest.
                data["transcript_source"] = "raw_then_recap"
                print(f"    Recap fallback recovered {len(motions)} motion(s).")
            else:
                print(f"    Recap fallback also returned 0 motions.")

        # Record API cost in the journal regardless of parse success,
        # so daily aggregates capture failed-extraction spend too.
        try:
            from pipeline_journal import PipelineJournal
            PipelineJournal(conn, RICHMOND_FIPS).log_api_cost(
                target_artifact="transcript_vote_extraction",
                model="claude-sonnet-5",
                input_tokens=stats["input_tokens"],
                output_tokens=stats["output_tokens"],
                approx_cost=stats["approx_cost"],
                extra={
                    "meeting_date": meeting_date,
                    "transcript_source": data["transcript_source"],
                    "motion_count": (len(motions) if motions is not None else 0),
                },
            )
        except Exception:
            pass  # journal writes are non-fatal

        if motions is None:
            print(f"    Parse failed (cost ${stats['approx_cost']:.4f})")
            return {"status": "parse_failed", "meeting_date": meeting_date,
                    "transcript_source": data["transcript_source"], **stats}

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
                    "motion_count": len(motions),
                    "transcript_source": data["transcript_source"], **stats}

        inserted = _insert_motions(
            conn, data["meeting_id"], data["agenda_items"],
            data["council"], motions,
        )
        return {"status": "extracted", "meeting_date": meeting_date,
                "motion_count": inserted,
                "transcript_source": data["transcript_source"], **stats}
    finally:
        conn.close()


def extract_all(dry_run: bool = False, force: bool = False) -> list[dict]:
    """Run extraction for every eligible meeting.

    Without `force`, skips meetings that already have ANY motions (transcript-
    or minutes-sourced). The minutes-source filter alone is not sufficient:
    a meeting that already has transcript-source motions from a prior run
    would otherwise be re-extracted on every `--enrich` pass — paying the
    full Claude API cost just to DELETE+re-INSERT the same rows. When
    minutes arrive later, db.load_meeting_to_db deletes the transcript-
    source motions, which makes the meeting eligible again for one final
    pass that gets superseded by minutes_extraction.

    With `force`, processes every meeting that has a recap (used for
    explicit regeneration after prompt changes).
    """
    sys.path.insert(0, str(Path(__file__).parent))
    from db import get_connection

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if force:
                cur.execute(
                    """SELECT m.meeting_date::text
                       FROM meetings m
                       WHERE m.city_fips = %s
                         AND m.meeting_type = 'regular'
                         AND m.transcript_recap IS NOT NULL
                       ORDER BY m.meeting_date DESC
                    """,
                    (RICHMOND_FIPS,),
                )
            else:
                cur.execute(
                    """SELECT m.meeting_date::text
                       FROM meetings m
                       WHERE m.city_fips = %s
                         AND m.meeting_type = 'regular'
                         AND m.transcript_recap IS NOT NULL
                         AND NOT EXISTS (
                           SELECT 1 FROM motions mo
                           JOIN agenda_items ai ON ai.id = mo.agenda_item_id
                           WHERE ai.meeting_id = m.id
                         )
                       ORDER BY m.meeting_date DESC
                    """,
                    (RICHMOND_FIPS,),
                )
            dates = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    label = "no motions yet" if not force else "force regenerate"
    print(f"Found {len(dates)} eligible meeting(s) (recap present, {label})")
    return [extract_meeting(d, dry_run=dry_run) for d in dates]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meeting-date", help="YYYY-MM-DD")
    parser.add_argument("--all", action="store_true",
                        help="Extract for every eligible meeting")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show extraction without writing to DB")
    parser.add_argument("--force", action="store_true",
                        help="Re-extract even meetings that already have motions")
    args = parser.parse_args()

    if not args.meeting_date and not args.all:
        parser.error("--meeting-date or --all required")

    if args.all:
        results = extract_all(dry_run=args.dry_run, force=args.force)
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
