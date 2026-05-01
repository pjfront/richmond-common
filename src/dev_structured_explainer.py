"""
One-shot test harness for the Locunity-style structured vote explainer.

Runs the new generator against a single meeting + agenda_item and prints
the structured JSON to stdout. Used during the rebuild for before/after
comparisons; kept as a development tool for prompt iteration.

Usage:
  python test_structured_explainer.py --meeting-date 2026-04-28 --item Q.3
  python test_structured_explainer.py --meeting-date 2026-04-28 --item Q.3 --skip-window
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

TRANSCRIPTS_DIR = Path(__file__).parent.parent / "data" / "transcripts"
RICHMOND_FIPS = "0660620"


def load_window(meeting_date: str, item_number: str) -> dict | None:
    path = TRANSCRIPTS_DIR / f"{meeting_date}_windows.json"
    if not path.exists():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    for w in doc.get("windows", []):
        if w.get("agenda_item_number") == item_number:
            return w
    return None


def load_motion_context(conn, meeting_date: str, item_number: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT m.id AS meeting_id, ai.id AS agenda_item_id,
                      ai.title, ai.description, ai.category, ai.department,
                      ai.financial_amount, ai.plain_language_summary,
                      mo.id AS motion_id, mo.motion_text, mo.motion_type,
                      mo.moved_by, mo.seconded_by, mo.result, mo.vote_tally,
                      mo.vote_explainer
               FROM meetings m
               JOIN agenda_items ai ON ai.meeting_id = m.id
               JOIN motions mo ON mo.agenda_item_id = ai.id
               WHERE m.city_fips = %s
                 AND m.meeting_date = %s
                 AND ai.item_number = %s
               ORDER BY mo.sequence_number ASC
               LIMIT 1
            """,
            (RICHMOND_FIPS, meeting_date, item_number),
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = [d[0] for d in cur.description]
        ctx = dict(zip(cols, row))

        cur.execute(
            """SELECT official_name, vote_choice
               FROM votes
               WHERE motion_id = %s
               ORDER BY official_name
            """,
            (ctx["motion_id"],),
        )
        ctx["votes"] = [
            {"official_name": r[0], "vote_choice": r[1]}
            for r in cur.fetchall()
        ]

        cur.execute(
            """SELECT name, role FROM officials
               WHERE city_fips = %s AND is_current = TRUE
               ORDER BY role DESC, seat NULLS LAST
            """,
            (RICHMOND_FIPS,),
        )
        ctx["council_roster"] = [
            {"name": r[0], "role": r[1]} for r in cur.fetchall()
        ]

        # Public comments for this item, if the table exists
        try:
            cur.execute(
                """SELECT speaker_name, comment_text, summary
                   FROM public_comments
                   WHERE agenda_item_id = %s
                   ORDER BY sequence_number NULLS LAST
                   LIMIT 50
                """,
                (ctx["agenda_item_id"],),
            )
            ctx["public_comments"] = [
                {"speaker_name": r[0], "comment_text": r[1], "summary": r[2]}
                for r in cur.fetchall()
            ]
        except Exception:
            ctx["public_comments"] = []

    return ctx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting-date", required=True)
    parser.add_argument("--item", required=True, help="agenda_items.item_number, e.g. Q.3")
    parser.add_argument("--skip-window", action="store_true",
                        help="Run without transcript window (for before/after comparison)")
    args = parser.parse_args()

    from db import get_connection
    from vote_explainer import generate_structured_vote_explainer

    conn = get_connection()
    ctx = load_motion_context(conn, args.meeting_date, args.item)
    if not ctx:
        print(f"No motion found for {args.meeting_date} {args.item}", file=sys.stderr)
        sys.exit(1)

    window = None if args.skip_window else load_window(args.meeting_date, args.item)
    if window:
        print(f"# Transcript window loaded: {window['char_count']} chars, "
              f"confidence={window['confidence']:.2f}", file=sys.stderr)
    else:
        print(f"# No transcript window {'(skipped)' if args.skip_window else 'available'}",
              file=sys.stderr)

    print(f"# Existing vote_explainer (current production):", file=sys.stderr)
    print(f"#   {ctx.get('vote_explainer') or '(none)'}\n", file=sys.stderr)

    result = generate_structured_vote_explainer(
        item_title=ctx["title"],
        item_description=ctx.get("description"),
        category=ctx.get("category"),
        department=ctx.get("department"),
        financial_amount=ctx.get("financial_amount"),
        plain_language_summary=ctx.get("plain_language_summary"),
        motion_text=ctx["motion_text"],
        motion_type=ctx.get("motion_type"),
        moved_by=ctx.get("moved_by"),
        seconded_by=ctx.get("seconded_by"),
        result=ctx["result"],
        vote_tally=ctx.get("vote_tally"),
        votes=ctx["votes"],
        council_roster=ctx["council_roster"],
        public_comments=ctx.get("public_comments"),
        transcript_window=window,
    )

    print(f"# Generated structured explainer", file=sys.stderr)
    print(f"# model={result['model']}", file=sys.stderr)
    print(f"# input_tokens={result['input_tokens']} output_tokens={result['output_tokens']} "
          f"cost=${result['approx_cost']:.4f}", file=sys.stderr)
    print(f"# transcript_window_used={result['transcript_window_used']}\n", file=sys.stderr)

    if result["structured"]:
        print(json.dumps(result["structured"], indent=2))
    else:
        print("# Failed to parse JSON. Raw response:", file=sys.stderr)
        print(result["raw_response"])

    conn.close()


if __name__ == "__main__":
    main()
