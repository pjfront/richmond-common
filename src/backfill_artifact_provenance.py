"""
Backfill *_provenance columns for rows generated before migration 095.

Provenance must be inferred from current state — for example, a
meeting_recap row written before this migration didn't carry source
information at write time, so we derive it now from whatever the
underlying motions look like at backfill time. Each backfilled row gets
`backfilled: true` so future audits can distinguish derived vs. directly-
recorded provenance.

Idempotent: only updates rows where `*_provenance IS NULL`. Safe to
re-run; safe to interrupt.

Usage:
    python backfill_artifact_provenance.py             # all six artifacts
    python backfill_artifact_provenance.py --dry-run   # show counts only
    python backfill_artifact_provenance.py --only meeting_recap
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

import provenance as prov  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ── Per-artifact backfill functions ────────────────────────────────────


def _backfill_meeting_recap(cur, dry_run: bool) -> int:
    """meeting_recap: pre-migration recaps had a strict source='minutes'
    motion gate, so backfill is unambiguous — kind='official_minutes'.
    """
    cur.execute(
        "SELECT id, minutes_url FROM meetings "
        "WHERE meeting_recap IS NOT NULL AND meeting_recap_provenance IS NULL"
    )
    rows = cur.fetchall()
    logger.info(f"meeting_recap: {len(rows)} rows to backfill")
    if dry_run:
        return len(rows)

    for mid, minutes_url in rows:
        p = prov.official_minutes(
            minutes_url=minutes_url,
            generator="generate_meeting_recaps.py",
            backfilled=True,
        )
        cur.execute(
            "UPDATE meetings SET meeting_recap_provenance = %s WHERE id = %s",
            (prov.to_json(p), mid),
        )
    return len(rows)


def _backfill_meeting_summary(cur, dry_run: bool) -> int:
    """meeting_summary: weak vote gate (any motion). Backfill kind from
    the current motion-source breakdown for that meeting.
    """
    cur.execute(
        """SELECT m.id,
                  COUNT(*) FILTER (WHERE COALESCE(mo.source, 'minutes') = 'minutes')   AS from_minutes,
                  COUNT(*) FILTER (WHERE COALESCE(mo.source, 'minutes') = 'transcript') AS from_transcript
           FROM meetings m
           JOIN agenda_items ai ON ai.meeting_id = m.id
           JOIN motions mo ON mo.agenda_item_id = ai.id
           WHERE m.meeting_summary IS NOT NULL
             AND m.meeting_summary_provenance IS NULL
           GROUP BY m.id"""
    )
    rows = cur.fetchall()
    logger.info(f"meeting_summary: {len(rows)} rows to backfill")
    if dry_run:
        return len(rows)

    for mid, from_minutes, from_transcript in rows:
        p = prov.mixed(
            from_minutes=from_minutes,
            from_transcript=from_transcript,
            generator="generate_meeting_summaries.py",
            backfilled=True,
        )
        cur.execute(
            "UPDATE meetings SET meeting_summary_provenance = %s WHERE id = %s",
            (prov.to_json(p), mid),
        )
    return len(rows)


def _backfill_orientation_preview(cur, dry_run: bool) -> int:
    """orientation_preview: always agenda_packet kind."""
    cur.execute(
        "SELECT id, agenda_url FROM meetings "
        "WHERE orientation_preview IS NOT NULL AND orientation_preview_provenance IS NULL"
    )
    rows = cur.fetchall()
    logger.info(f"orientation_preview: {len(rows)} rows to backfill")
    if dry_run:
        return len(rows)

    for mid, agenda_url in rows:
        p = prov.agenda_packet(
            agenda_url=agenda_url,
            generator="generate_orientation_previews.py",
            backfilled=True,
        )
        cur.execute(
            "UPDATE meetings SET orientation_preview_provenance = %s WHERE id = %s",
            (prov.to_json(p), mid),
        )
    return len(rows)


def _backfill_transcript_recap(cur, dry_run: bool) -> int:
    """transcript_recap: kind='meeting_recording'. Channel inferred from
    the existing transcript_recap_source flat column ('youtube' → kcrt).
    """
    cur.execute(
        "SELECT id, transcript_recap_source FROM meetings "
        "WHERE transcript_recap IS NOT NULL AND transcript_recap_provenance IS NULL"
    )
    rows = cur.fetchall()
    logger.info(f"transcript_recap: {len(rows)} rows to backfill")
    if dry_run:
        return len(rows)

    for mid, source in rows:
        # Default to kcrt; the only existing transcripts come from KCRT
        # YouTube uploads. If a granicus channel ever lands, the
        # generator writing it will set the provenance directly.
        channel = "kcrt"
        p = prov.meeting_recording(
            channel=channel,
            generator="post_meeting_recap.py",
            backfilled=True,
        )
        cur.execute(
            "UPDATE meetings SET transcript_recap_provenance = %s WHERE id = %s",
            (prov.to_json(p), mid),
        )
    return len(rows)


def _backfill_bio_summary(cur, dry_run: bool) -> int:
    """bio_summary: derive {from_minutes, from_transcript} from each
    official's current votes table breakdown. Mirrors get_vote_source_breakdown
    in generate_bios.py.
    """
    cur.execute(
        """SELECT o.id,
                  COUNT(*) FILTER (WHERE COALESCE(v.source, 'minutes') = 'minutes')   AS from_minutes,
                  COUNT(*) FILTER (WHERE COALESCE(v.source, 'minutes') = 'transcript') AS from_transcript
           FROM officials o
           LEFT JOIN votes v ON v.official_id = o.id
           WHERE o.bio_summary IS NOT NULL
             AND o.bio_summary_provenance IS NULL
           GROUP BY o.id"""
    )
    rows = cur.fetchall()
    logger.info(f"bio_summary: {len(rows)} rows to backfill")
    if dry_run:
        return len(rows)

    for oid, from_minutes, from_transcript in rows:
        if from_minutes == 0 and from_transcript == 0:
            # Bio with no current votes — leave provenance NULL, the
            # render will fall back to the pre-provenance footer string.
            continue
        p = prov.mixed(
            from_minutes=from_minutes,
            from_transcript=from_transcript,
            generator="generate_bios.py",
            backfilled=True,
        )
        cur.execute(
            "UPDATE officials SET bio_summary_provenance = %s WHERE id = %s",
            (prov.to_json(p), oid),
        )
    return len(rows)


def _backfill_plain_language_summary(cur, dry_run: bool) -> int:
    """plain_language_summary: always agenda_packet kind."""
    cur.execute(
        """SELECT ai.id, m.agenda_url
           FROM agenda_items ai
           JOIN meetings m ON m.id = ai.meeting_id
           WHERE ai.plain_language_summary IS NOT NULL
             AND ai.plain_language_summary_provenance IS NULL"""
    )
    rows = cur.fetchall()
    logger.info(f"plain_language_summary: {len(rows)} rows to backfill")
    if dry_run:
        return len(rows)

    # Batch updates in chunks of 1000 — large table.
    for i, (item_id, agenda_url) in enumerate(rows):
        p = prov.agenda_packet(
            agenda_url=agenda_url,
            generator="generate_summaries.py",
            backfilled=True,
        )
        cur.execute(
            "UPDATE agenda_items SET plain_language_summary_provenance = %s WHERE id = %s",
            (prov.to_json(p), item_id),
        )
        if (i + 1) % 1000 == 0:
            logger.info(f"  ...{i + 1}/{len(rows)}")
    return len(rows)


# ── Orchestration ─────────────────────────────────────────────────────


_BACKFILLERS = {
    "meeting_recap": _backfill_meeting_recap,
    "meeting_summary": _backfill_meeting_summary,
    "orientation_preview": _backfill_orientation_preview,
    "transcript_recap": _backfill_transcript_recap,
    "bio_summary": _backfill_bio_summary,
    "plain_language_summary": _backfill_plain_language_summary,
}


def main():
    parser = argparse.ArgumentParser(description="Backfill artifact provenance")
    parser.add_argument("--dry-run", action="store_true", help="Show counts only")
    parser.add_argument(
        "--only", choices=list(_BACKFILLERS.keys()),
        help="Backfill a single artifact (default: all)",
    )
    args = parser.parse_args()

    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])

    targets = [args.only] if args.only else list(_BACKFILLERS.keys())
    totals = {}

    try:
        with conn.cursor() as cur:
            for name in targets:
                count = _BACKFILLERS[name](cur, args.dry_run)
                totals[name] = count
            if not args.dry_run:
                conn.commit()
    finally:
        conn.close()

    prefix = "[DRY RUN] " if args.dry_run else ""
    logger.info(f"\n{prefix}Backfill totals:")
    for name, count in totals.items():
        logger.info(f"  {name}: {count}")


if __name__ == "__main__":
    main()
