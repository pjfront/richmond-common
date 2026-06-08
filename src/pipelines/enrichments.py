"""
enrichments pipeline module — extracted from data_sync.py (Phase 2.3).

Each sync_X function is registered in data_sync.SYNC_SOURCES and dispatched
by data_sync.run_sync. Module-level helpers (enrichments-specific) live alongside.
"""
from __future__ import annotations

import anthropic_budget_lock  # noqa: F401  # must import before anthropic SDK (installs cost/cap/kill-switch gate); sync_proceeding_classification calls the API directly

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
    from generate_meeting_summaries import generate_summaries

    result = generate_summaries(conn, city_fips, force=(sync_type == "full"))

    return {
        "records_fetched": result["total"],
        "records_new": result["generated"],
        "records_updated": 0,
        "skipped": result.get("skipped", 0),
        "errors": result.get("errors", 0),
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
    from generate_orientation_previews import generate_previews

    result = generate_previews(conn, city_fips, force=(sync_type == "full"))

    return {
        "records_fetched": result["total"],
        "records_new": result["generated"],
        "records_updated": 0,
        "skipped": result.get("skipped", 0),
        "errors": result.get("errors", 0),
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
    from generate_meeting_recaps import generate_recaps

    result = generate_recaps(conn, city_fips, force=(sync_type == "full"))

    return {
        "records_fetched": result["total"],
        "records_new": result["generated"],
        "records_updated": 0,
        "skipped": result.get("skipped", 0),
        "errors": result.get("errors", 0),
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
    n_extracted = sum(1 for r in results if r["status"] == "extracted")
    n_skipped = sum(1 for r in results if r["status"] == "skipped")
    n_motions = sum(r.get("motion_count", 0) for r in results)
    n_errors = sum(1 for r in results if r["status"] in ("parse_failed",))
    return {
        "records_fetched": len(results),
        "records_new": n_motions,
        "records_updated": 0,
        "skipped": n_skipped,
        "errors": n_errors,
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
    from generate_comment_summaries import generate_comment_summaries as gen_summaries

    result = gen_summaries(conn, city_fips, force=(sync_type == "full"))

    return {
        "records_fetched": result["total"],
        "records_new": result["generated"],
        "records_updated": 0,
        "skipped": result.get("skipped", 0),
        "errors": result.get("errors", 0),
    }



def sync_topic_tagging(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Tag agenda items with local civic topics (keyword-based, zero API cost).

    Idempotent: ON CONFLICT updates existing assignments.
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

    return {
        "records_fetched": len(items),
        "records_new": generated,
        "records_updated": 0,
        "skipped": skipped,
        "errors": errors,
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

    contributions = _fetch_contributions_from_db(conn, city_fips)
    expenditures = _fetch_expenditures_from_db(conn, city_fips)
    independent_expenditures = _fetch_independent_expenditures_from_db(conn, city_fips)
    permits = _fetch_permits_from_db(conn, city_fips)
    licenses = _fetch_licenses_from_db(conn, city_fips)
    behested = _fetch_behested_from_db(conn, city_fips)
    lobbyists = _fetch_lobbyists_from_db(conn, city_fips)
    try:
        entity_graph = load_entity_graph(conn, city_fips)
        org_reverse_map = load_org_reverse_map(conn, city_fips)
    except Exception:
        entity_graph, org_reverse_map = {}, {}

    total_flags = 0
    meetings_scanned = 0

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
            import uuid as _uuid
            scan_run_id = create_scan_run(
                conn, city_fips,
                meeting_id=meeting_id,
                scan_mode="prospective",
                data_cutoff_date=meeting_date,
                triggered_by="enrichment",
            )

            # Supersede old flags + save new ones
            supersede_flags_for_meeting(conn, meeting_id, scan_run_id, "prospective")
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

    return {
        "records_fetched": len(unscanned),
        "records_new": total_flags,
        "records_updated": 0,
        "meetings_scanned": meetings_scanned,
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

    return {
        "records_fetched": len(motions),
        "records_new": generated,
        "records_updated": 0,
        "skipped": skipped,
        "errors": errors,
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
    from theme_extractor import get_items_needing_themes, extract_themes_for_item

    items = get_items_needing_themes(city_fips, include_stale=True)
    if not items:
        return {"records_fetched": 0, "records_new": 0, "records_updated": 0}

    extracted = 0
    errors = 0
    for item in items:
        try:
            extract_themes_for_item(item["agenda_item_id"])
            extracted += 1
        except Exception as e:
            print(f"    Theme error for item {item.get('agenda_item_id')}: {e}")
            errors += 1

    return {
        "records_fetched": len(items),
        "records_new": extracted,
        "records_updated": 0,
        "errors": errors,
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


def sync_proceeding_classification(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Classify agenda items by proceeding type (resolution, ordinance, etc.).

    For incremental sync: uses direct Claude API calls for small batches.
    For full backfill: use batch_classify_proceeding.py CLI instead.
    """
    import psycopg2.extras

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """SELECT count(*) FROM agenda_items ai
               JOIN meetings m ON m.id = ai.meeting_id
               WHERE m.city_fips = %s AND ai.proceeding_type IS NULL
               AND LENGTH(ai.title) >= 10""",
            (city_fips,),
        )
        pending = cur.fetchone()[0]

    if pending == 0:
        return {"records_fetched": 0, "records_new": 0, "records_updated": 0}

    # For incremental (small batches < 100), classify directly
    # For large backfill, log the count and advise using the batch CLI
    if pending > 100:
        print(f"  {pending} items need proceeding type classification.")
        print(f"  For large backfills, use: python batch_classify_proceeding.py export && submit && import")
        return {
            "records_fetched": pending,
            "records_new": 0,
            "records_updated": 0,
            "note": f"{pending} items pending — use batch CLI for bulk classification",
        }

    # Small batch: classify directly via Claude API
    import anthropic as _anthropic

    client = _anthropic.Anthropic()
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

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """SELECT ai.id, ai.title, ai.description, ai.category,
                      ai.is_consent_calendar, ai.financial_amount, ai.resolution_number
               FROM agenda_items ai
               JOIN meetings m ON m.id = ai.meeting_id
               WHERE m.city_fips = %s AND ai.proceeding_type IS NULL
               AND LENGTH(ai.title) >= 10
               LIMIT 100""",
            (city_fips,),
        )
        items = cur.fetchall()

    classified = 0
    for item in items:
        parts = [f"Title: {item['title']}"]
        if item["description"] and len(item["description"]) > 10:
            parts.append(f"Description: {item['description'][:1000]}")
        if item["resolution_number"]:
            parts.append(f"Resolution number: {item['resolution_number']}")
        if item["financial_amount"]:
            parts.append(f"Financial amount: {item['financial_amount']}")
        if item["category"]:
            parts.append(f"Category: {item['category']}")
        parts.append(f"Consent calendar: {'Yes' if item['is_consent_calendar'] else 'No'}")

        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=20,
                temperature=0,  # Deterministic single-token classification; default 1.0 produces output variance.
                system=system_prompt,
                messages=[{"role": "user", "content": "\n".join(parts)}],
            )
            ptype = response.content[0].text.strip().lower().strip('"\'.- ')
            if ptype in valid_types:
                with conn.cursor() as cur2:
                    cur2.execute(
                        "UPDATE agenda_items SET proceeding_type = %s WHERE id = %s",
                        (ptype, item["id"]),
                    )
                classified += 1
        except Exception as e:
            print(f"  Classification error for {item['id']}: {e}")
            continue

    conn.commit()
    return {
        "records_fetched": len(items),
        "records_new": classified,
        "records_updated": 0,
    }


