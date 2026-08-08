"""
enrichments pipeline module — extracted from data_sync.py (Phase 2.3).

Each sync_X function is registered in data_sync.SYNC_SOURCES and dispatched
by data_sync.run_sync. Module-level helpers (enrichments-specific) live alongside.
"""
from __future__ import annotations


import json
import os
import time
from datetime import datetime
from pathlib import Path

import psycopg2

from city_config import get_city_config, list_configured_cities
from db import (
    get_connection,
    create_sync_log,
    complete_sync_log,
    load_contributions_to_db,
    load_expenditures_to_db,
)
from pipeline_journal import PipelineJournal, check_anomalies

DEFAULT_FIPS = "0660620"


# A nullable enrichment output is not, by itself, evidence of pending work.
# These read-only gates pair each output with the source material its generator
# actually needs. They keep the weekly enrichment sweep from repeatedly opening
# generators that can only return ``skipped`` for permanently inapplicable rows.
_PENDING_ENRICHMENT_SQL = {
    "meeting_summary": """
        SELECT EXISTS (
            SELECT 1
            FROM meetings m
            WHERE m.city_fips = %s
              AND m.meeting_summary IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM agenda_items ai
                  JOIN motions mo ON mo.agenda_item_id = ai.id
                  WHERE ai.meeting_id = m.id
                    AND ai.agenda_source_retired_at IS NULL
              )
              AND EXISTS (
                  SELECT 1
                  FROM agenda_items ai
                  WHERE ai.meeting_id = m.id
                    AND ai.agenda_source_retired_at IS NULL
                    AND ai.category <> 'procedural'
                    AND NULLIF(BTRIM(CONCAT_WS(
                        ' ', ai.title, ai.summary_headline, ai.description
                    )), '') IS NOT NULL
              )
        )
    """,
    "orientation_preview": """
        SELECT EXISTS (
            SELECT 1
            FROM meetings m
            WHERE m.city_fips = %s
              AND m.orientation_preview IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM agenda_items ai
                  WHERE ai.meeting_id = m.id
                    AND ai.agenda_source_retired_at IS NULL
                    AND ai.category <> 'procedural'
                    AND NULLIF(BTRIM(CONCAT_WS(
                        ' ', ai.title, ai.summary_headline,
                        ai.plain_language_summary, ai.topic_label
                    )), '') IS NOT NULL
              )
        )
    """,
    "meeting_recap": """
        SELECT EXISTS (
            SELECT 1
            FROM meetings m
            WHERE m.city_fips = %s
              AND m.meeting_recap IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM agenda_items ai
                  JOIN motions mo ON mo.agenda_item_id = ai.id
                  WHERE ai.meeting_id = m.id
                    AND ai.agenda_source_retired_at IS NULL
                    AND mo.source = 'minutes'
              )
              AND EXISTS (
                  SELECT 1
                  FROM agenda_items ai
                  WHERE ai.meeting_id = m.id
                    AND ai.agenda_source_retired_at IS NULL
                    AND ai.category <> 'procedural'
                    AND NULLIF(BTRIM(CONCAT_WS(
                        ' ', ai.title, ai.summary_headline,
                        ai.plain_language_summary
                    )), '') IS NOT NULL
              )
        )
    """,
    "comment_summary": """
        SELECT EXISTS (
            SELECT 1
            FROM agenda_items ai
            JOIN meetings m ON m.id = ai.meeting_id
            WHERE m.city_fips = %s
              AND ai.agenda_source_retired_at IS NULL
              AND ai.ai_comment_summary IS NULL
              AND ai.public_comment_count > 0
              AND (
                  EXISTS (
                      SELECT 1 FROM public_comments pc
                      WHERE pc.agenda_item_id = ai.id
                  )
                  OR EXISTS (
                      SELECT 1 FROM item_theme_narratives itn
                      WHERE itn.agenda_item_id = ai.id
                        AND itn.confidence >= 0.7
                  )
              )
        )
    """,
    "topic_label": """
        SELECT EXISTS (
            SELECT 1
            FROM agenda_items ai
            JOIN meetings m ON m.id = ai.meeting_id
            WHERE m.city_fips = %s
              AND ai.agenda_source_retired_at IS NULL
              AND ai.topic_label IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM item_topics it
                  JOIN topics t ON t.id = it.topic_id
                  WHERE it.agenda_item_id = ai.id
                    AND t.status = 'active'
              )
        )
    """,
}


def _has_pending_enrichment(conn, enrichment: str, city_fips: str) -> bool:
    """Return whether an incremental enrichment has eligible source data.

    This deliberately fails closed when the query errors: running a costly
    generator without proving eligibility would recreate the control-plane
    amplification this guard exists to prevent.
    """
    try:
        query = _PENDING_ENRICHMENT_SQL[enrichment]
    except KeyError as exc:
        raise ValueError(f"Unknown enrichment eligibility gate: {enrichment}") from exc

    with conn.cursor() as cur:
        cur.execute(query, (city_fips,))
        row = cur.fetchone()
    return bool(row and row[0])


def _empty_sync_result() -> dict:
    """Return the standard no-work result without sharing mutable state."""
    return {"records_fetched": 0, "records_new": 0, "records_updated": 0}


def _retryable_incomplete_fields(
    failed_count: int,
    failure_summary: str,
    *,
    details: list[str] | None = None,
) -> dict:
    """Return the common explicit contract for best-effort partial failure.

    The durable source-change coordinator intentionally does not guess from
    wrapper-specific counters such as ``errors`` or ``failed``. Every wrapper
    that catches a row/meeting failure must therefore opt in explicitly here.
    Empty/no-work results continue to use :func:`_empty_sync_result`.
    """
    count = int(failed_count)
    if count < 0:
        raise ValueError("failed_count cannot be negative")
    if count == 0:
        return {
            "retryable_incomplete": False,
            "incomplete_count": 0,
            "incomplete_reasons": [],
        }

    reasons = [failure_summary.strip() or f"{count} enrichment unit(s) failed"]
    for detail in details or []:
        rendered = str(detail).strip()
        if rendered and rendered not in reasons:
            reasons.append(rendered[:300])
        if len(reasons) >= 5:
            break
    return {
        "retryable_incomplete": True,
        "incomplete_count": count,
        "incomplete_reasons": reasons,
    }


def sync_meeting_summaries(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Generate meeting-level summaries for meetings with vote data but no summary.

    This is a derived/enrichment sync — it processes meetings that already have
    motions and votes extracted. Should run after minutes_extraction.

    Calls the Claude API to generate 3-5 bullet narrative summaries.
    """
    if sync_type != "full" and not _has_pending_enrichment(
        conn, "meeting_summary", city_fips,
    ):
        return _empty_sync_result()

    from generate_meeting_summaries import generate_summaries

    result = generate_summaries(conn, city_fips, force=(sync_type == "full"))
    errors = int(result.get("errors", 0) or 0)

    return {
        "records_fetched": result["total"],
        "records_new": result["generated"],
        "records_updated": 0,
        "skipped": result.get("skipped", 0),
        "errors": errors,
        **_retryable_incomplete_fields(
            errors,
            f"{errors} meeting summary generation attempt(s) failed",
        ),
    }


def sync_orientation_previews(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
    **kwargs,
) -> dict:
    """Generate pre-meeting orientation previews for meetings without one.

    This is a derived/enrichment sync — it processes meetings that have
    extracted agenda items but no orientation_preview yet. Unlike meeting
    summaries, orientations don't require votes/minutes (no vote gate).

    Calls the Claude API to generate 3-5 paragraph narrative previews.
    """
    if sync_type != "full" and not _has_pending_enrichment(
        conn, "orientation_preview", city_fips,
    ):
        return _empty_sync_result()

    from generate_orientation_previews import generate_previews

    result = generate_previews(conn, city_fips, force=(sync_type == "full"))
    errors = int(result.get("errors", 0) or 0)

    return {
        "records_fetched": result["total"],
        "records_new": result["generated"],
        "records_updated": 0,
        "skipped": result.get("skipped", 0),
        "errors": errors,
        **_retryable_incomplete_fields(
            errors,
            f"{errors} orientation preview generation attempt(s) failed",
        ),
    }


def sync_meeting_recaps(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
    **kwargs,
) -> dict:
    """Generate post-meeting narrative recaps for meetings without one.

    This is a derived/enrichment sync — it processes meetings that have
    votes/motions but no meeting_recap yet. Richer than meeting_summary
    (bullets): produces 4-6 paragraph narrative with vote breakdowns,
    community voice themes, and continued items.

    Calls the Claude API to generate narrative recaps.
    """
    if sync_type != "full" and not _has_pending_enrichment(
        conn, "meeting_recap", city_fips,
    ):
        return _empty_sync_result()

    from generate_meeting_recaps import generate_recaps

    result = generate_recaps(conn, city_fips, force=(sync_type == "full"))
    errors = int(result.get("errors", 0) or 0)

    return {
        "records_fetched": result["total"],
        "records_new": result["generated"],
        "records_updated": 0,
        "skipped": result.get("skipped", 0),
        "errors": errors,
        **_retryable_incomplete_fields(
            errors,
            f"{errors} meeting recap generation attempt(s) failed",
        ),
    }


def sync_transcript_windowing(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
    **kwargs,
) -> dict:
    """Generate per-agenda-item transcript windows for meetings whose raw
    transcript is persisted but {date}_windows.json is missing.

    Reads `data/transcripts/{date}_clean.txt` (the source-closest persisted
    transcript) and writes `data/transcripts/{date}_windows.json`. One
    Claude call per meeting (~$0.20-0.30) produces per-item start/end
    timestamp markers; Python deterministically slices the raw transcript
    on those markers — the LLM never emits transcript content, only marker
    strings, so source-closest discipline is preserved end-to-end.

    Wraps window_meeting_transcript.window_meeting(). Surfaces in
    SYNC_SOURCES so the pipeline manifest's `transcript_windowing`
    enrichment entry has a real callable (previously declared but
    unregistered, causing the SessionStart "drift" warning).

    Idempotent: incremental skips meetings with an existing _windows.json.
    sync_type='full' regenerates regardless. Under
    RICHMOND_API_BUDGET_LOCK (PR #26 kill switch), the first window_meeting
    call raises AnthropicBudgetLockError before tokens are billed, the
    loop short-circuits, and the function returns errs > 0.

    Single-tenant for now (Richmond-only transcripts on disk). Multi-city
    expansion would require a per-city TRANSCRIPTS_DIR.
    """
    if city_fips != "0660620":
        return {
            "records_fetched": 0,
            "records_new": 0,
            "records_updated": 0,
            "skipped": 0,
            "errors": 0,
        }

    from window_meeting_transcript import window_meeting, TRANSCRIPTS_DIR

    force = (sync_type == "full")
    fetched = new = errs = skipped = 0
    failure_details: list[str] = []
    for path in sorted(TRANSCRIPTS_DIR.glob("*_clean.txt")):
        meeting_date = path.stem.removesuffix("_clean")
        fetched += 1
        windows_path = TRANSCRIPTS_DIR / f"{meeting_date}_windows.json"
        if not force and windows_path.exists():
            skipped += 1
            continue
        result = window_meeting(conn, meeting_date)
        if result.get("error"):
            errs += 1
            failure_details.append(
                f"Transcript windowing failed for {meeting_date}: "
                f"{result.get('error')}"
            )
        elif result.get("skipped"):
            skipped += 1
        else:
            new += 1
    return {
        "records_fetched": fetched,
        "records_new": new,
        "records_updated": 0,
        "skipped": skipped,
        "errors": errs,
        **_retryable_incomplete_fields(
            errs,
            f"{errs} transcript windowing meeting(s) failed",
            details=failure_details,
        ),
    }


def sync_transcript_votes(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
    **kwargs,
) -> dict:
    """Extract preliminary motions+votes from transcript_recap text.

    Downstream of recap_generation. For each meeting that has a
    transcript_recap but no motions yet, parses vote outcomes from the
    transcript using Claude and writes them with source='transcript'.
    When minutes arrive later, minutes_extraction (via db.load_meeting_to_db)
    deletes these and inserts source='minutes' rows.

    Cost: ~$0.20-0.30 per meeting on raw transcripts. Idempotent in the
    incremental path: meetings that already have any motions are skipped,
    so re-running this sync after the first successful pass is a no-op.
    Use sync_type='full' to force re-extraction (e.g., after a prompt
    change that warrants regeneration).
    """
    from extract_transcript_votes import extract_all

    results = extract_all(dry_run=False, force=(sync_type == "full"))
    n_skipped = sum(1 for r in results if r["status"] == "skipped")
    n_motions = sum(r.get("motion_count", 0) for r in results)
    terminal_success_statuses = {"extracted", "skipped", "no_recap"}
    failed_results = [
        result
        for result in results
        if result.get("status") not in terminal_success_statuses
    ]
    n_errors = len(failed_results)
    failure_details = [
        f"Transcript vote extraction for "
        f"{result.get('meeting_date', 'unknown meeting')} returned "
        f"{result.get('status', 'missing status')}"
        for result in failed_results
    ]
    return {
        "records_fetched": len(results),
        "records_new": n_motions,
        "records_updated": 0,
        "skipped": n_skipped,
        "errors": n_errors,
        **_retryable_incomplete_fields(
            n_errors,
            f"{n_errors} transcript vote extraction meeting(s) failed",
            details=failure_details,
        ),
    }


def sync_comment_summaries(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
    **kwargs,
) -> dict:
    """Generate AI comment summaries for agenda items with public testimony.

    This is a derived/enrichment sync — it processes agenda items that have
    public_comment_count > 0 but no comment_summary yet.
    """
    if sync_type != "full" and not _has_pending_enrichment(
        conn, "comment_summary", city_fips,
    ):
        return _empty_sync_result()

    from generate_comment_summaries import generate_comment_summaries as gen_summaries

    result = gen_summaries(conn, city_fips, force=(sync_type == "full"))
    errors = int(result.get("errors", 0) or 0)

    return {
        "records_fetched": result["total"],
        "records_new": result["generated"],
        "records_updated": 0,
        "skipped": result.get("skipped", 0),
        "errors": errors,
        **_retryable_incomplete_fields(
            errors,
            f"{errors} public comment summary generation attempt(s) failed",
        ),
    }



def sync_topic_tagging(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Tag agenda items with local civic topics (keyword-based, zero API cost).

    Hard-idempotent: the conflict branch updates only when assignment values
    changed; identical matches produce no database write.
    """
    from topic_tagger import backfill_topics

    result = backfill_topics(conn, city_fips)
    return {
        "records_fetched": result["items_scanned"],
        "records_new": result["assignments_created"],
        "records_updated": 0,
        "items_tagged": result["items_tagged"],
    }


def sync_item_summaries(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Generate plain-language summaries for agenda items missing them.

    Uses Claude API. Skips procedural items.

    Cost: ~$0.02 per agenda item (measured 2026-05-25 from pipeline_journal
    api_cost rows under event_type='escribemeetings', avg $0.021/call). The
    earlier "$0.07/meeting" figure in this docstring was stale; see D68 in
    docs/AI-PARKING-LOT.md for the broader lesson on per-item cost drift +
    the backlog-magnification effect when unblocking idempotent cascades.
    """
    from generate_summaries import (
        get_items_needing_summaries,
        generate_summary_for_item,
        should_summarize,
    )
    from topic_tagger import get_topic_label_seeds, format_topic_seed_prompt, backfill_topic_labels

    # Pre-populate topic_label from curated item_topics before LLM fills gaps.
    # This ensures items matched by keyword-based topic_tagging get their
    # curated label ("Police & Community Safety") instead of a bespoke LLM
    # label ("Police SWAT Equipment"). Must run after topic_tagging.
    if _has_pending_enrichment(conn, "topic_label", city_fips):
        backfill_stats = backfill_topic_labels(conn, city_fips)
        if backfill_stats["items_updated"] > 0:
            print(f"    Backfilled {backfill_stats['items_updated']} topic labels from curated topics")
            conn.commit()

    items = get_items_needing_summaries(
        conn, city_fips, force=(sync_type == "full"),
    )
    if not items:
        return {"records_fetched": 0, "records_new": 0, "records_updated": 0}

    seeds = get_topic_label_seeds(conn, city_fips)
    topic_seed_prompt = format_topic_seed_prompt(seeds)

    generated = 0
    skipped = 0
    errors = 0
    failure_details: list[str] = []
    for item in items:
        try:
            result = generate_summary_for_item(
                conn, item, topic_seed_prompt=topic_seed_prompt,
            )
            if result.get("skipped"):
                skipped += 1
            else:
                generated += 1
                time.sleep(0.3)  # Rate limit
        except Exception as e:
            print(f"    Summary error for {item.get('id')}: {e}")
            errors += 1
            failure_details.append(
                f"Agenda item {item.get('id', 'unknown')}: {type(e).__name__}: {e}"
            )

    return {
        "records_fetched": len(items),
        "records_new": generated,
        "records_updated": 0,
        "skipped": skipped,
        "errors": errors,
        **_retryable_incomplete_fields(
            errors,
            f"{errors} agenda item summary generation attempt(s) failed",
            details=failure_details,
        ),
    }


def sync_conflict_scanning(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Scan meetings for conflicts of interest (zero API cost).

    Finds meetings that have never been scanned, loads all reference data
    from the database, and runs the full v3 scanner. Preserves scan_runs
    audit trail and flag supersession.
    """
    from conflict_scanner import scan_meeting_db
    from db import (
        create_scan_run,
        save_conflict_flag,
        supersede_flags_for_meeting,
    )

    # Find meetings without a scan_run
    with conn.cursor() as cur:
        cur.execute(
            """SELECT m.id, m.meeting_date
               FROM meetings m
               WHERE m.city_fips = %s
                 AND EXISTS (
                   SELECT 1 FROM agenda_items ai
                   WHERE ai.meeting_id = m.id
                     AND ai.agenda_source_retired_at IS NULL
                 )
                 AND NOT EXISTS (
                     SELECT 1 FROM scan_runs sr
                     WHERE sr.meeting_id = m.id AND sr.status = 'completed'
                 )
               ORDER BY m.meeting_date DESC""",
            (city_fips,),
        )
        unscanned = cur.fetchall()

    if not unscanned:
        return {"records_fetched": 0, "records_new": 0, "records_updated": 0}

    print(f"  Found {len(unscanned)} meetings needing conflict scan")

    # Pre-load shared reference data once (expensive queries)
    from conflict_scanner import (
        _fetch_contributions_from_db,
        _fetch_form700_interests_from_db,
        _fetch_expenditures_from_db,
        _fetch_independent_expenditures_from_db,
        _fetch_permits_from_db,
        _fetch_licenses_from_db,
        _fetch_behested_from_db,
        _fetch_lobbyists_from_db,
    )
    from db import load_entity_graph, load_org_reverse_map

    try:
        contributions = _fetch_contributions_from_db(conn, city_fips)
        expenditures = _fetch_expenditures_from_db(conn, city_fips)
        independent_expenditures = _fetch_independent_expenditures_from_db(
            conn, city_fips,
        )
        permits = _fetch_permits_from_db(conn, city_fips)
        licenses = _fetch_licenses_from_db(conn, city_fips)
        behested = _fetch_behested_from_db(conn, city_fips)
        lobbyists = _fetch_lobbyists_from_db(conn, city_fips)
        # Reference-read failures are not evidence of an empty signal family.
        # Fail before creating/completing any scan_run so the durable
        # coordinator retries with every detector input present.
        entity_graph = load_entity_graph(conn, city_fips)
        org_reverse_map = load_org_reverse_map(conn, city_fips)
    except Exception:
        # A failed SQL read may leave the transaction aborted. Restore the
        # connection so run_sync can persist its failed sync log, then retry.
        conn.rollback()
        raise

    total_flags = 0
    meetings_scanned = 0
    meetings_failed = 0
    failure_details: list[str] = []

    for meeting_id, meeting_date in unscanned:
        print(f"  Scanning {meeting_date} ({meeting_id})...")
        try:
            # Per-meeting: fetch form700 interests with meeting date context
            form700 = _fetch_form700_interests_from_db(
                conn, city_fips, meeting_date,
            )

            scan_result = scan_meeting_db(
                conn, str(meeting_id), city_fips,
                contributions=contributions,
                form700_interests=form700,
                expenditures=expenditures,
                independent_expenditures=independent_expenditures,
                permits=permits,
                licenses=licenses,
                entity_graph=entity_graph,
                org_reverse_map=org_reverse_map,
                behested_payments=behested,
                lobbyist_registrations=lobbyists,
            )

            # Create scan run record
            scan_run_id = create_scan_run(
                conn, city_fips,
                meeting_id=meeting_id,
                scan_mode="prospective",
                data_cutoff_date=meeting_date,
                triggered_by="enrichment",
                commit=False,
            )

            # Supersede old flags + save new ones
            supersede_flags_for_meeting(
                conn,
                meeting_id,
                scan_run_id,
                "prospective",
                commit=False,
            )
            for flag in scan_result.flags:
                evidence_json = (
                    [{"text": e} for e in flag.evidence] if flag.evidence else []
                )
                save_conflict_flag(
                    conn,
                    city_fips=city_fips,
                    meeting_id=meeting_id,
                    scan_run_id=scan_run_id,
                    flag_type=flag.flag_type,
                    description=flag.description,
                    evidence=evidence_json,
                    confidence=flag.confidence,
                    scan_mode="prospective",
                    data_cutoff_date=meeting_date,
                    legal_reference=flag.legal_reference,
                    publication_tier=flag.publication_tier,
                    confidence_factors=flag.confidence_factors,
                    scanner_version=flag.scanner_version,
                    match_details=flag.match_details,
                    commit=False,
                )

            # Mark scan run complete
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE scan_runs SET status = 'completed',
                       flags_found = %s, completed_at = NOW()
                       WHERE id = %s""",
                    (len(scan_result.flags), scan_run_id),
                )
            conn.commit()

            total_flags += len(scan_result.flags)
            meetings_scanned += 1
            print(f"    {len(scan_result.flags)} flags found")

        except Exception as e:
            print(f"    ERROR scanning {meeting_date}: {e}")
            meetings_failed += 1
            failure_details.append(
                f"Conflict scan failed for {meeting_date} ({meeting_id}): "
                f"{type(e).__name__}: {e}"
            )
            # A failed statement aborts the current PostgreSQL transaction.
            # Roll back this meeting so later independent meetings can run.
            conn.rollback()

    return {
        "records_fetched": len(unscanned),
        "records_new": total_flags,
        "records_updated": 0,
        "meetings_scanned": meetings_scanned,
        "failed": meetings_failed,
        "errors": meetings_failed,
        **_retryable_incomplete_fields(
            meetings_failed,
            f"{meetings_failed} meeting conflict scan(s) failed",
            details=failure_details,
        ),
    }


def sync_vote_explainers(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Generate vote explainers for motions missing them.

    Uses Claude API. Only processes motions that have votes (skips upcoming meetings).
    """
    from generate_vote_explainers import (
        get_motions_needing_explainers,
        generate_explainer_for_motion,
    )

    motions = get_motions_needing_explainers(
        conn, city_fips, force=(sync_type == "full"),
    )
    if not motions:
        return {"records_fetched": 0, "records_new": 0, "records_updated": 0}

    generated = 0
    skipped = 0
    errors = 0
    failure_details: list[str] = []
    for motion in motions:
        try:
            result = generate_explainer_for_motion(conn, motion)
            if result.get("skipped"):
                skipped += 1
            else:
                generated += 1
                time.sleep(0.3)
        except Exception as e:
            print(f"    Explainer error for motion {motion.get('motion_id')}: {e}")
            errors += 1
            failure_details.append(
                f"Motion {motion.get('motion_id', 'unknown')}: "
                f"{type(e).__name__}: {e}"
            )

    return {
        "records_fetched": len(motions),
        "records_new": generated,
        "records_updated": 0,
        "skipped": skipped,
        "errors": errors,
        **_retryable_incomplete_fields(
            errors,
            f"{errors} vote explainer generation attempt(s) failed",
            details=failure_details,
        ),
    }


def sync_theme_extraction(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Extract themes from public comments (items with 3+ comments).

    Uses Claude API. Only processes items that have enough comments.
    """
    from theme_extractor import (
        MIN_COMMENTS,
        extract_themes_for_item,
        get_comments_for_item,
        get_existing_theme_seeds,
        get_items_needing_themes,
        import_themes,
    )

    items = get_items_needing_themes(city_fips, include_stale=True)
    if not items:
        return {"records_fetched": 0, "records_new": 0, "records_updated": 0}

    extracted = 0
    skipped = 0
    errors = 0
    failure_details: list[str] = []
    seeds = get_existing_theme_seeds(city_fips)
    for item in items:
        try:
            item_id = item["item_id"]
            comments = get_comments_for_item(item_id)
            if len(comments) < MIN_COMMENTS:
                skipped += 1
                continue
            result = extract_themes_for_item(item, comments, seeds)
            if not result:
                raise ValueError("theme extractor returned no valid result")
            stats = import_themes(
                result,
                item_id,
                comments,
                city_fips=city_fips,
            )
            extracted += 1
            if stats.get("themes_created", 0) > 0:
                seeds = get_existing_theme_seeds(city_fips)
        except Exception as e:
            item_id = item.get("item_id", "unknown")
            print(f"    Theme error for item {item_id}: {e}")
            errors += 1
            failure_details.append(
                f"Agenda item {item_id}: {type(e).__name__}: {e}"
            )

    return {
        "records_fetched": len(items),
        "records_new": extracted,
        "records_updated": 0,
        "skipped": skipped,
        "errors": errors,
        **_retryable_incomplete_fields(
            errors,
            f"{errors} public comment theme extraction attempt(s) failed",
            details=failure_details,
        ),
    }



def sync_embedding_generation(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Generate embeddings for content tables missing them.

    Uses OpenAI text-embedding-3-small (~$0.02/M tokens). Idempotent:
    skips rows that already have embeddings. Gracefully skips if
    OPENAI_API_KEY is not configured (Layer 3 is optional until S25).
    """
    if not os.getenv("OPENAI_API_KEY"):
        print("  Skipping embedding_generation: OPENAI_API_KEY not configured")
        return {"records_fetched": 0, "records_new": 0, "records_updated": 0}

    from embedding_generator import embed_table, get_coverage_stats

    total = 0
    for table in ("agenda_items", "meetings", "officials", "motions"):
        count = embed_table(conn, table, city_fips=city_fips)
        total += count

    stats = get_coverage_stats(conn, city_fips=city_fips)
    return {
        "records_fetched": sum(s["total"] for s in stats.values()),
        "records_new": total,
        "records_updated": 0,
        "coverage": {k: f"{v['embedded']}/{v['total']}" for k, v in stats.items()},
    }


def _count_unresolved_proceeding_classifications(conn, city_fips: str) -> int:
    """Count all retryable rows, including rows leased by another worker."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT count(*) FROM agenda_items ai
               JOIN meetings m ON m.id = ai.meeting_id
               WHERE m.city_fips = %s
               AND ai.agenda_source_retired_at IS NULL
               AND ai.proceeding_type IS NULL
               AND LENGTH(ai.title) >= 10
               AND ai.proceeding_classification_attempts < 3""",
            (city_fips,),
        )
        return int(cur.fetchone()[0])


def _proceeding_incomplete_fields(pending_remaining: int) -> dict:
    """Return the healthy-continuation contract for this bounded slice.

    Remaining rows are not a failed delivery: the wrapper intentionally caps
    each paid invocation at 100 rows.  Systemic provider/configuration errors
    raise, while row-level invalid output is persisted against that row's own
    three-attempt budget.  The durable event coordinator can therefore queue
    another slice without spending its separate failure/dead-letter budget.
    """
    return {
        "pending_remaining": pending_remaining,
        "retryable_incomplete": False,
        "incomplete_count": 0,
        "incomplete_reasons": [],
        "continuation_required": pending_remaining > 0,
        "continuation_count": pending_remaining,
        "continuation_reasons": (
            [
                f"{pending_remaining} proceeding classification(s) "
                "remain after this bounded slice"
            ]
            if pending_remaining
            else []
        ),
    }


def sync_proceeding_classification(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Classify agenda items by proceeding type (resolution, ordinance, etc.).

    For incremental sync: uses direct routed LLM calls for small batches.
    For full backfill: use batch_classify_proceeding.py CLI instead.

    Failed or structurally invalid rows are attempted at most three times.
    Persisted attempt state keeps poison rows from consuming every LIMIT 100
    slice and starving later agenda items.
    """
    import psycopg2.extras
    import uuid

    # Count every unresolved retryable row, not only currently claimable
    # rows. A live lease held by another worker is still incomplete and must
    # prevent a durable change-event from terminally acknowledging.
    pending = _count_unresolved_proceeding_classifications(conn, city_fips)

    if pending == 0:
        return {
            "records_fetched": 0,
            "records_new": 0,
            "records_updated": 0,
            **_proceeding_incomplete_fields(0),
        }

    # Process a bounded synchronous slice. Provider batch operations are
    # deliberately quarantined until their upload/status/result contract is
    # integration-tested, so large backfills converge across repeated runs.
    if pending > 100:
        print(f"  {pending} items pending; processing the next 100 synchronously.")

    from llm_client import LLMClient, ROUTINE_MODEL

    client = LLMClient()
    # Prompts live in src/prompts/, not src/pipelines/prompts/. This file
    # used to be src/data_sync.py (Phase 2.3 split, commit 18a3386 on
    # 2026-05-11) where Path(__file__).parent / "prompts" resolved
    # correctly. The move into src/pipelines/ left the path stale —
    # __file__ now resolves one directory deeper, so the path needs
    # .parent.parent. tests/test_pipeline_prompts.py enforces every
    # prompt path under src/pipelines/ resolves to a real file, so the
    # next instance of this refactor-class bug fails at PR time.
    prompt_path = Path(__file__).parent.parent / "prompts" / "proceeding_type_system.txt"
    system_prompt = prompt_path.read_text(encoding="utf-8").strip()

    valid_types = {
        "resolution", "ordinance", "contract", "appropriation",
        "appointment", "hearing", "proclamation", "report",
        "censure", "appeal", "consent", "other",
    }

    claim_token = uuid.uuid4()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """WITH candidates AS (
                 SELECT ai.id
                 FROM agenda_items ai
                 JOIN meetings m ON m.id = ai.meeting_id
                 WHERE m.city_fips = %s
                   AND ai.agenda_source_retired_at IS NULL
                   AND ai.proceeding_type IS NULL
                   AND LENGTH(ai.title) >= 10
                   AND ai.proceeding_classification_attempts < 3
                   AND (
                     ai.proceeding_classification_claim_token IS NULL
                     OR ai.proceeding_classification_claim_expires_at < NOW()
                   )
                 ORDER BY ai.proceeding_classification_attempts ASC,
                          m.meeting_date DESC NULLS LAST,
                          ai.id ASC
                 FOR UPDATE OF ai SKIP LOCKED
                 LIMIT 100
               )
               UPDATE agenda_items ai
               SET proceeding_classification_claim_token = %s,
                   proceeding_classification_claim_expires_at =
                     NOW() + INTERVAL '3 hours'
               FROM candidates c
               WHERE ai.id = c.id
               RETURNING ai.id, ai.title, ai.description, ai.category,
                         ai.is_consent_calendar, ai.financial_amount,
                         ai.resolution_number,
                         ai.proceeding_classification_attempts""",
            (city_fips, claim_token),
        )
        items = cur.fetchall()
    # Publish the lease before making any paid request. A concurrent worker
    # then skips these rows; a crashed worker's lease becomes eligible later.
    conn.commit()

    if not items:
        pending_remaining = _count_unresolved_proceeding_classifications(
            conn, city_fips,
        )
        return {
            "records_fetched": 0,
            "records_new": 0,
            "records_updated": 0,
            "remaining_eligible_before_run": pending,
            **_proceeding_incomplete_fields(pending_remaining),
        }

    classified = 0
    failed = 0
    dead_lettered = 0

    class ProceedingClassificationOutputError(ValueError):
        """A paid response completed but did not prove a valid label."""

    def record_failure(item_id, prior_attempts: int, detail: str) -> None:
        nonlocal failed, dead_lettered
        final_attempt = prior_attempts + 1 >= 3
        with conn.cursor() as cur2:
            cur2.execute(
                """UPDATE agenda_items
                   SET proceeding_classification_attempts =
                         LEAST(proceeding_classification_attempts + 1, 3),
                       proceeding_classification_last_error = %s,
                       proceeding_classification_last_attempted_at = NOW(),
                       proceeding_classification_dead_lettered_at =
                         CASE WHEN proceeding_classification_attempts + 1 >= 3
                              THEN NOW()
                              ELSE proceeding_classification_dead_lettered_at
                         END,
                       proceeding_classification_claim_token = NULL,
                       proceeding_classification_claim_expires_at = NULL
                   WHERE id = %s
                     AND proceeding_classification_claim_token = %s""",
                (detail[:500], item_id, claim_token),
            )
            owned = cur2.rowcount == 1
        if owned:
            failed += 1
            if final_attempt:
                dead_lettered += 1

    def release_remaining_claims() -> None:
        with conn.cursor() as cur2:
            cur2.execute(
                """UPDATE agenda_items
                   SET proceeding_classification_claim_token = NULL,
                       proceeding_classification_claim_expires_at = NULL
                   WHERE proceeding_classification_claim_token = %s""",
                (claim_token,),
            )

    for item in items:
        try:
            parts = [f"Title: {item['title']}"]
            if item["description"] and len(item["description"]) > 10:
                parts.append(f"Description: {item['description'][:1000]}")
            if item["resolution_number"]:
                parts.append(f"Resolution number: {item['resolution_number']}")
            if item["financial_amount"]:
                parts.append(f"Financial amount: {item['financial_amount']}")
            if item["category"]:
                parts.append(f"Category: {item['category']}")
            parts.append(
                f"Consent calendar: {'Yes' if item['is_consent_calendar'] else 'No'}"
            )

            response = client.messages.create(
                model=ROUTINE_MODEL,
                max_tokens=20,
                temperature=0,
                system=system_prompt,
                messages=[{"role": "user", "content": "\n".join(parts)}],
            )
            if response.stop_reason == "max_tokens":
                raise ProceedingClassificationOutputError(
                    "classification response reached max_tokens"
                )
            text_blocks = [
                block.text
                for block in response.content
                if getattr(block, "type", None) == "text"
                and getattr(block, "text", None)
            ]
            if not text_blocks:
                raise ProceedingClassificationOutputError(
                    "classification response contained no text"
                )
            ptype = " ".join(text_blocks).strip().lower().strip('"\'.- ')
            if ptype in valid_types:
                with conn.cursor() as cur2:
                    cur2.execute(
                        """UPDATE agenda_items
                           SET proceeding_type = %s,
                               proceeding_classification_attempts =
                                 LEAST(proceeding_classification_attempts + 1, 3),
                               proceeding_classification_last_error = NULL,
                               proceeding_classification_last_attempted_at = NOW(),
                               proceeding_classification_dead_lettered_at = NULL,
                               proceeding_classification_claim_token = NULL,
                               proceeding_classification_claim_expires_at = NULL
                           WHERE id = %s
                             AND proceeding_classification_claim_token = %s""",
                        (ptype, item["id"], claim_token),
                    )
                    owned = cur2.rowcount == 1
                if owned:
                    classified += 1
            else:
                raise ProceedingClassificationOutputError(
                    f"unexpected label: {ptype!r}"
                )
        except ProceedingClassificationOutputError as e:
            print(f"  Classification error for {item['id']}: {e}")
            record_failure(
                item["id"],
                int(item["proceeding_classification_attempts"] or 0),
                f"{type(e).__name__}: {e}",
            )
        except Exception:
            # Provider/network/budget/router/configuration failures are
            # systemic, not evidence that this agenda row is poison. Release
            # every unprocessed lease and let the coordinator retry/fail.
            release_remaining_claims()
            conn.commit()
            raise

    conn.commit()
    pending_remaining = _count_unresolved_proceeding_classifications(
        conn, city_fips,
    )
    return {
        "records_fetched": len(items),
        "records_new": classified,
        "records_updated": failed,
        "dead_lettered": dead_lettered,
        "remaining_eligible_before_run": pending,
        **_proceeding_incomplete_fields(pending_remaining),
    }


