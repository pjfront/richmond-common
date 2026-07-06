"""
Richmond Common — Unified Data Source Sync

Syncs external data sources to Supabase with logging and observability.
Each sync creates a data_sync_log entry for tracking freshness.

Supported sources:
  - netfile: Local campaign contributions (NetFile Connect2 API)
  - calaccess: State PAC/IE contributions (CAL-ACCESS bulk download)
  - escribemeetings: Meeting agendas and documents
  - nextrequest: CPRA public records requests (NextRequest portal)
  - archive_center: CivicPlus Archive Center documents (resolutions, ordinances, etc.)
  - form700: Form 700 financial disclosures (NetFile SEI portal)
  - socrata_payroll: City employee payroll (Socrata open data)
  - socrata_expenditures: City spending records (Socrata open data)
  - elections: Election cycle tracking (derived from committee/contribution data)

Usage:
  python data_sync.py --source netfile
  python data_sync.py --source calaccess
  python data_sync.py --source netfile --triggered-by n8n
  python data_sync.py --source netfile --sync-type full
"""
from __future__ import annotations

import llm_budget_lock  # noqa: F401  # must import before LLM SDK
from llm_budget_lock import (
    AnthropicBudgetLockError,
    AnthropicEventCapError,
    AnthropicMonthlyCapError,
)
import inspect
import io
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding for Unicode characters in Socrata data etc.
# Without this, print() fails with 'charmap' codec errors on cp1252 consoles.
# Guard: only wrap if not already UTF-8, and detach old wrapper to avoid
# closing the underlying buffer (which breaks pytest capture on teardown).
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    if getattr(sys.stdout, "encoding", "").lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if getattr(sys.stderr, "encoding", "").lower() != "utf-8":
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from city_config import get_city_config, list_configured_cities
from db import (
    get_connection,
    create_sync_log,
    complete_sync_log,
    load_contributions_to_db,
    load_expenditures_to_db,
)

import psycopg2

from pipeline_journal import PipelineJournal, check_anomalies

DEFAULT_FIPS = "0660620"  # Richmond — keep as CLI default for backward compat


# ── Enrichment Sync Functions ─────────────────────────────────
# These follow the same (conn, city_fips, ...) -> dict contract as sync
# sources but process data already in the database. Each detects its own
# new work — idempotent, zero-cost when nothing needs doing.
# See also: sync_meeting_summaries, sync_written_comments (same pattern).


# ── Downstream Enrichment Runner ─────────────────────────────


def run_downstream(
    source: str,
    conn,
    city_fips: str,
    triggered_by: str = "enrichment",
) -> list[dict]:
    """After a source sync, run all downstream enrichments from the manifest DAG.

    Uses pipeline_map.py's PipelineGraph to walk from source → tables →
    enrichments. Only runs enrichments that exist in SYNC_SOURCES (the
    manifest may describe enrichments not yet wired up). Each enrichment
    detects its own new work, so this is safe to call repeatedly.
    """
    from pipeline_map import load_manifest, PipelineGraph

    manifest = load_manifest()
    graph = PipelineGraph(manifest)

    source_key = graph.find_node(source)
    if not source_key:
        print(f"  WARNING: Source '{source}' not found in pipeline manifest")
        return []

    downstream = graph.trace_downstream(source_key)
    enrichment_names = [
        n.split(":", 1)[1]
        for n in downstream
        if n.startswith("enrichment:")
    ]

    if not enrichment_names:
        print(f"  No downstream enrichments for {source}")
        return []

    # Filter to pure enrichments: in SYNC_SOURCES, in manifest enrichments
    # section, but NOT also a source (excludes derived extractors like
    # minutes_extraction that appear as both source and enrichment).
    manifest_enrichments = set(manifest.get("enrichments", {}).keys())
    manifest_sources = set(manifest.get("sources", {}).keys())
    runnable = [
        name for name in enrichment_names
        if name in SYNC_SOURCES
        and name in manifest_enrichments
        and name not in manifest_sources
    ]
    if not runnable:
        print(f"  Downstream enrichments {enrichment_names} not yet in SYNC_SOURCES")
        return []

    print(f"\n{'=' * 50}")
    print(f"  DOWNSTREAM ENRICHMENTS for {source}")
    print(f"  Running: {', '.join(runnable)}")
    print(f"{'=' * 50}\n")

    results = []
    for name in runnable:
        print(f"── Enrichment: {name} ──")
        try:
            result = run_sync(
                source=name,
                city_fips=city_fips,
                triggered_by=triggered_by,
            )
            results.append({"enrichment": name, **result})
        except Exception as e:
            print(f"  ERROR in {name}: {e}")
            results.append({"enrichment": name, "status": "failed", "error": str(e)})

    return results


# ── Pipeline imports (Phase 2.3) ─────────────────────────────
# Each sync_* function is defined in src/pipelines/<group>.py.
# Tests that patch `data_sync.get_connection` etc. keep working —
# those module-level imports remain at the top of this file.
from donor_classifier import sync_donor_classification  # noqa: E402
from pipelines.netfile import (  # noqa: E402
    sync_netfile,
    sync_donor_employer_merge,
    sync_paper_filing_reconciliation,
    sync_donor_dedup,
)
from pipelines.calaccess import (  # noqa: E402
    sync_calaccess,
)
# Private helpers used by tests via `from data_sync import _X` — re-exported
# for backwards compatibility.
from pipelines.socrata import (  # noqa: E402,F401
    _normalize_vendor_name,
    _parse_socrata_date,
    _safe_numeric,
    _safe_int,
)
from pipelines.escribemeetings import (  # noqa: E402
    sync_escribemeetings,
    sync_escribemeetings_minutes,
    backfill_escribemeetings_layer2,
    sync_minutes_extraction,
    refresh_stale_minutes,
    submit_minutes_batch,
    collect_minutes_batch,
)
from pipelines.nextrequest import (  # noqa: E402
    sync_nextrequest,
)
from pipelines.archive_center import (  # noqa: E402
    sync_archive_center,
    sync_written_comments,
)
from pipelines.form700 import (  # noqa: E402
    sync_form700,
)
from pipelines.socrata import (  # noqa: E402
    sync_socrata_payroll,
    sync_socrata_expenditures,
    sync_socrata_permits,
    sync_socrata_licenses,
    sync_socrata_code_cases,
    sync_socrata_service_requests,
    sync_socrata_projects,
)
from pipelines.external import (  # noqa: E402
    sync_courts,
    sync_propublica,
    sync_form803_behested,
    sync_lobbyist_registrations,
    sync_opencorporates,
)
from pipelines.elections import (  # noqa: E402
    sync_elections,
    sync_filing_period_briefings,
)
from pipelines.enrichments import (  # noqa: E402
    sync_meeting_summaries,
    sync_orientation_previews,
    sync_meeting_recaps,
    sync_transcript_votes,
    sync_transcript_windowing,
    sync_comment_summaries,
    sync_topic_tagging,
    sync_item_summaries,
    sync_conflict_scanning,
    sync_vote_explainers,
    sync_theme_extraction,
    sync_embedding_generation,
    sync_proceeding_classification,
)


SYNC_SOURCES = {
    "netfile": sync_netfile,
    "calaccess": sync_calaccess,
    "escribemeetings": sync_escribemeetings,
    "escribemeetings_minutes": sync_escribemeetings_minutes,
    "nextrequest": sync_nextrequest,
    "archive_center": sync_archive_center,
    "form700": sync_form700,
    "minutes_extraction": sync_minutes_extraction,
    "socrata_payroll": sync_socrata_payroll,
    "socrata_expenditures": sync_socrata_expenditures,
    "socrata_permits": sync_socrata_permits,
    "socrata_licenses": sync_socrata_licenses,
    "socrata_code_cases": sync_socrata_code_cases,
    "socrata_service_requests": sync_socrata_service_requests,
    "socrata_projects": sync_socrata_projects,
    "courts": sync_courts,
    "propublica": sync_propublica,
    "form803_behested": sync_form803_behested,
    "lobbyist_registrations": sync_lobbyist_registrations,
    "opencorporates": sync_opencorporates,
    "elections": sync_elections,
    "meeting_summaries": sync_meeting_summaries,
    "refresh_stale_minutes": refresh_stale_minutes,
    "written_comments": sync_written_comments,
    # Enrichments (same contract, detect their own new work)
    "topic_tagging": sync_topic_tagging,
    "summary_generation": sync_item_summaries,
    "conflict_scanning": sync_conflict_scanning,
    "vote_explainer_generation": sync_vote_explainers,
    "theme_extraction": sync_theme_extraction,
    "meeting_summary_generation": sync_meeting_summaries,  # alias
    "orientation_generation": sync_orientation_previews,
    "recap_generation": sync_meeting_recaps,
    "transcript_vote_extraction": sync_transcript_votes,
    "transcript_windowing": sync_transcript_windowing,
    "comment_summary_generation": sync_comment_summaries,
    "embedding_generation": sync_embedding_generation,
    "proceeding_classification": sync_proceeding_classification,
    "filing_period_briefing_generation": sync_filing_period_briefings,
    # Donor-table integrity. These run AFTER netfile sync via the manifest
    # DAG so cross-filing dups and employer-key fragmentation get caught
    # before downstream enrichments (filing_period_briefing, conflict
    # scanning) read the contributions/donors tables. Order matters:
    # employer merge first (collapses donor rows), then cross-filing dedup
    # (which keys on donor_id and benefits from the merge).
    "donor_employer_merge": sync_donor_employer_merge,
    "donor_dedup": sync_donor_dedup,
    "paper_filing_reconciliation": sync_paper_filing_reconciliation,
    "donor_classification": sync_donor_classification,
}


# Severity floor for routing anomalies into the operator decision_queue.
# Anything below this stays journal-only. "high" = >100% deviation from the
# rolling median (see detect_count_anomaly). Tighten later if too noisy.
_ANOMALY_HOLD_SEVERITIES = {"high"}


def _route_anomalies_to_decision_queue(
    conn,
    city_fips: str,
    source: str,
    anomalies: list[dict],
) -> int:
    """Create decision_queue rows for HIGH-severity sync anomalies.

    The sync itself still completes — the data is committed to the DB —
    but a P0 row appears in the operator decision_queue so the next
    SessionStart brief surfaces "Sync anomaly hold" at the top of the
    risk summary. The operator reviews before downstream consumers
    (frontend ISR, email digests, journalist-visible pages) start
    treating the spike as routine.

    Why this is separate from the journal: log_anomaly already journals
    every detected anomaly, but journal entries are passive — they sit
    until someone looks. The decision_queue row is active — it counts
    toward the P0 number on the SessionStart brief and shows up in
    `decision_queue` UI / queries.

    Returns the number of holds created (0 if no high-severity anomalies
    or if decision_queue creation failed silently).

    See T0.4 of plans/steady-crafting-island.md for the motivating
    incident (2026-05-16 contributions sync reported records_new=1591
    against a baseline of ~6 and AI presented it as "verified").
    """
    created = 0
    try:
        # Lazy import — keep module-level imports clean and avoid a cycle
        # if decision_queue ever needs to log via PipelineJournal.
        from decision_queue import create_decision
    except Exception as exc:
        print(f"  [decision_queue] import failed; skipping holds: {exc}")
        return 0

    for anom in anomalies:
        severity = anom.get("severity", "medium")
        if severity not in _ANOMALY_HOLD_SEVERITIES:
            continue

        step_name = anom.get("step_name") or f"sync_{source}"
        current = anom.get("current") if "current" in anom else anom.get("current_seconds")
        baseline = anom.get("baseline") if "baseline" in anom else anom.get("average_seconds")
        deviation_pct = anom.get("deviation_pct")
        ratio = anom.get("ratio")

        if "deviation_pct" in anom:
            # Count anomaly
            magnitude_clause = f"{deviation_pct}% deviation"
        elif "ratio" in anom:
            # Timing anomaly
            magnitude_clause = f"{ratio}x normal duration"
        else:
            magnitude_clause = "anomaly"

        title = (
            f"Sync hold: {source} {step_name} — current={current}, "
            f"baseline={baseline} ({magnitude_clause})"
        )
        description = anom.get("description") or title

        # Dedup key shape: lets repeated runs of the same anomalous sync
        # produce ONE pending decision instead of stacking. Operator
        # resolves once; subsequent identical anomalies create a fresh
        # row (since the prior one is no longer "pending").
        dedup_key = f"sync_anomaly:{source}:{step_name}"

        try:
            decision_id = create_decision(
                conn,
                city_fips=city_fips,
                decision_type="anomaly",
                severity="critical",  # high-severity anomalies are P0
                title=title[:255],     # decision_queue title may be capped
                description=description,
                source="data_sync.check_anomalies",
                evidence=anom,
                dedup_key=dedup_key,
            )
            if decision_id:
                created += 1
                print(f"  [decision_queue] HOLD created: {title}")
            # decision_id is None if deduplicated; that's expected behavior
        except Exception as exc:
            # Never let decision_queue write failure kill the sync.
            print(f"  [decision_queue] failed to create hold: {exc}")

    return created


def run_sync(
    source: str,
    city_fips: str = DEFAULT_FIPS,
    sync_type: str = "incremental",
    triggered_by: str = "manual",
    pipeline_run_id: str = None,
    limit: int | None = None,
    max_retries: int = 2,
) -> dict:
    """Run a data sync for the specified source with automatic retry.

    Creates a data_sync_log entry, runs the sync, and updates the log.
    Retries up to max_retries times with exponential backoff on transient
    failures (network errors, HTTP 5xx, timeouts). Non-transient errors
    (e.g., bad config, missing tables) fail immediately.

    Returns a summary dict.
    """
    if source not in SYNC_SOURCES:
        raise ValueError(f"Unknown source '{source}'. Available: {', '.join(SYNC_SOURCES)}")

    # Validate city is configured
    city_cfg = get_city_config(city_fips)

    start_time = time.time()
    conn = get_connection()

    print(f"\n{'='*60}")
    print(f"Data Sync: {source} ({city_cfg['name']})")
    print(f"Type: {sync_type} | Triggered by: {triggered_by}")
    print(f"{'='*60}\n")

    sync_log_id = create_sync_log(
        conn,
        city_fips=city_fips,
        source=source,
        sync_type=sync_type,
        triggered_by=triggered_by,
        pipeline_run_id=pipeline_run_id,
    )
    print(f"Sync log: {sync_log_id}")

    journal = PipelineJournal(conn, city_fips)
    journal.log_run_start("data_sync", str(sync_log_id),
        f"Sync {source} ({sync_type}, triggered by {triggered_by})",
        {"source": source, "sync_type": sync_type, "triggered_by": triggered_by,
         "pipeline_run_id": pipeline_run_id})

    try:
        sync_fn = SYNC_SOURCES[source]
        extra = {"limit": limit} if source in ("minutes_extraction", "refresh_stale_minutes") and limit is not None else {}

        # Build kwargs from function signature — only pass args the function accepts
        def _build_call_args(fn, conn_val):
            params = inspect.signature(fn).parameters
            args = {"conn": conn_val, "city_fips": city_fips}
            if "sync_type" in params:
                args["sync_type"] = sync_type
            if "sync_log_id" in params:
                args["sync_log_id"] = sync_log_id
            args.update({k: v for k, v in extra.items() if k in params})
            return args

        # Retry loop with exponential backoff for transient failures
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    wait = min(30 * (2 ** (attempt - 1)), 120)  # 30s, 60s, 120s max
                    print(f"\n  Retry {attempt}/{max_retries} after {wait}s backoff...")
                    time.sleep(wait)
                    # Reconnect on retry — connection may be stale after error
                    try:
                        conn.close()
                    except Exception:
                        pass
                    conn = get_connection()
                    journal.conn = conn  # journal cached the old handle
                result = sync_fn(**_build_call_args(sync_fn, conn))
                last_error = None
                break  # Success
            except (AnthropicBudgetLockError, AnthropicMonthlyCapError,
                    AnthropicEventCapError):
                # Budget rails fired — never retry (the lock/cap won't
                # clear between attempts). Handled by the outer
                # skip-handler below.
                raise
            except (ConnectionError, TimeoutError, OSError,
                    psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                last_error = e
                print(f"\n  Transient error (attempt {attempt + 1}/{max_retries + 1}): {e}")
                if attempt == max_retries:
                    raise  # Final attempt — let outer handler catch it
            except Exception as e:
                # Check for HTTP 5xx or connection-related errors in message
                err_str = str(e).lower()
                if any(kw in err_str for kw in (
                    "500", "502", "503", "504", "timeout", "connection",
                    "ssl syscall", "eof detected", "server closed",
                )):
                    last_error = e
                    print(f"\n  Transient error (attempt {attempt + 1}/{max_retries + 1}): {e}")
                    if attempt == max_retries:
                        raise
                else:
                    raise  # Non-transient — fail immediately

        retries_used = attempt  # 0 if succeeded first try
        execution_time = time.time() - start_time
        meta = {"execution_seconds": round(execution_time, 2), **result}
        if retries_used > 0:
            meta["retries_used"] = retries_used
        complete_sync_log(
            conn,
            sync_log_id=sync_log_id,
            records_fetched=result.get("records_fetched"),
            records_new=result.get("records_new"),
            records_updated=result.get("records_updated"),
            metadata=meta,
        )

        log_meta = {
            "source": source,
            "records_fetched": result.get("records_fetched", 0),
            "records_new": result.get("records_new", 0),
            "records_updated": result.get("records_updated", 0),
            "execution_seconds": round(execution_time, 2),
        }
        if retries_used > 0:
            log_meta["retries_used"] = retries_used
        journal.log_run_end("data_sync", str(sync_log_id), "completed",
            f"Sync {source} complete in {execution_time:.1f}s"
            + (f" (after {retries_used} retries)" if retries_used > 0 else ""),
            log_meta)

        # Check for anomalies in sync results. HIGH-severity anomalies
        # (deviation > 100% from recent baseline) are routed into the
        # operator decision_queue as a "hold" so the operator sees a
        # P0 entry before downstream consumers see the data. The sync
        # itself still completes — the data is in the DB — but the
        # journalist/public-facing path doesn't get green-lit until
        # the operator confirms the spike is real.
        #
        # Motivating case: on 2026-05-16 a contributions sync reported
        # records_new: 1591 as "verified live end-to-end" when the
        # rolling baseline was ~6. The data was correct (a backlog
        # caught up), but the AI presented it to the operator as a
        # normal sync. With this hold in place, the operator would
        # have seen "Sync anomaly hold: netfile reported 1591 (baseline
        # 6) — review before publishing" at the top of the next
        # SessionStart brief and could have validated before acting.
        anomalies = check_anomalies(
            journal, conn, city_fips, f"sync_{source}",
            current_count=result.get("records_fetched"),
            current_seconds=execution_time,
            count_metric_key="records_fetched",
        )
        if anomalies:
            _route_anomalies_to_decision_queue(
                conn, city_fips, source, anomalies
            )

        print(f"\n{'='*60}")
        print(f"Sync complete: {source}")
        print(f"  Fetched: {result.get('records_fetched', 0)}")
        print(f"  New: {result.get('records_new', 0)}")
        print(f"  Time: {execution_time:.1f}s")
        print(f"{'='*60}")

        return {"sync_log_id": str(sync_log_id), "status": "completed", **result}

    except (AnthropicBudgetLockError, AnthropicMonthlyCapError,
            AnthropicEventCapError) as e:
        # ── P0.9: budget lock/cap = graceful skip, not error ──────
        # The budget rails firing is the safety system working as
        # designed. Counting it as a sync *failure* turns every locked
        # run red (the June 2026 freeze pattern). Instead: record an
        # 'enrichment_skipped' journal entry so the liveness layer can
        # see the skip, mark the sync log completed with skip metadata,
        # and return status='skipped'. Freshness expectations (e.g.
        # "meeting >5 days without recap", severity high) intentionally
        # do NOT pause on these skips — a cap-hit that silences
        # freshness alerting would rebuild the June freeze on purpose.
        execution_time = time.time() - start_time
        reason = "lock" if isinstance(e, AnthropicBudgetLockError) else "cap"
        print(f"\n[skipped: budget {reason}] Sync {source} skipped "
              f"after {execution_time:.1f}s: {e}")
        try:
            complete_sync_log(
                conn,
                sync_log_id=sync_log_id,
                metadata={
                    "skipped": True,
                    "skip_reason": reason,
                    "skip_detail": str(e),
                    "execution_seconds": round(execution_time, 2),
                },
            )
        except Exception as log_err:
            print(f"  WARNING: failed to record budget skip: {log_err}")
        journal.log_step(
            f"sync_{source}",
            f"{source} skipped: Anthropic budget {reason} active",
            {
                "enrichment": source,
                "reason": reason,
                "detail": str(e),
                "execution_seconds": round(execution_time, 2),
            },
            entry_type="enrichment_skipped",
        )
        journal.log_run_end(
            "data_sync", str(sync_log_id), "completed",
            f"Sync {source} skipped (budget {reason}) after "
            f"{execution_time:.1f}s",
            {"source": source, "skipped": True, "skip_reason": reason},
        )
        return {
            "sync_log_id": str(sync_log_id),
            "status": "skipped",
            "skip_reason": reason,
            "error": str(e),
        }

    except Exception as e:
        execution_time = time.time() - start_time
        print(f"\nERROR: Sync failed after {execution_time:.1f}s: {e}")
        # If the failure killed the DB connection itself (SSL EOF, server
        # closed mid-sync), the next write on the dead handle would raise
        # InterfaceError and mask the real error. Try once, then reconnect
        # and retry on connection-level failure.
        try:
            complete_sync_log(
                conn,
                sync_log_id=sync_log_id,
                error_message=str(e),
            )
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as log_err:
            print(f"  Connection dead while logging failure ({log_err}); reconnecting...")
            try:
                try:
                    conn.close()
                except Exception:
                    pass
                conn = get_connection()
                journal.conn = conn
                complete_sync_log(
                    conn,
                    sync_log_id=sync_log_id,
                    error_message=str(e),
                )
            except Exception as retry_err:
                print(f"  WARNING: failed to record sync failure: {retry_err}")
        try:
            journal.log_run_end("data_sync", str(sync_log_id), "failed",
                f"Sync {source} failed after {execution_time:.1f}s: {e}", {
                    "source": source,
                    "error": str(e),
                    "execution_seconds": round(execution_time, 2),
                })
        except Exception:
            pass  # journal is non-fatal
        return {"sync_log_id": str(sync_log_id), "status": "failed", "error": str(e)}
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ── CLI ──────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Richmond Common — Data Source Sync",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Available sources: {', '.join(SYNC_SOURCES)}

Examples:
  python data_sync.py --source netfile
  python data_sync.py --source calaccess --sync-type full
  python data_sync.py --source escribemeetings --triggered-by n8n
  python data_sync.py --backfill-layer2  # hydrate meetings table from existing eSCRIBE docs
  python data_sync.py --extract-minutes  # extract structured data from Archive Center minutes

Batch extraction (50% cost reduction):
  python data_sync.py --batch-extract                # submit all unextracted minutes
  python data_sync.py --batch-extract --limit 100    # submit up to 100
  python data_sync.py --batch-status BATCH_ID        # check if batch is done
  python data_sync.py --collect-batch BATCH_ID        # collect results and load to DB
        """,
    )
    # Separate enrichment names from external sources in the help text
    _external_sources = [k for k in SYNC_SOURCES if k not in {
        "topic_tagging", "summary_generation", "conflict_scanning",
        "vote_explainer_generation", "theme_extraction", "meeting_summary_generation",
        "orientation_generation", "recap_generation", "transcript_vote_extraction",
    }]
    parser.add_argument("--source", choices=list(SYNC_SOURCES), help="Data source to sync")
    parser.add_argument("--sync-type", choices=["full", "incremental"], default="incremental", help="Sync type")
    parser.add_argument("--triggered-by", default="manual", help="What triggered this sync")
    parser.add_argument("--city-fips", default=DEFAULT_FIPS, help="City FIPS code")
    parser.add_argument("--pipeline-run-id", help="GitHub Actions run ID or n8n execution ID")
    parser.add_argument("--max-retries", type=int, default=2,
        help="Max retry attempts for transient failures (default: 2)")
    parser.add_argument("--list-cities", action="store_true", help="List configured cities and exit")
    parser.add_argument(
        "--backfill-layer2",
        action="store_true",
        help="Hydrate Layer 2 (meetings/agenda_items) from existing eSCRIBE docs",
    )
    parser.add_argument(
        "--extract-minutes",
        action="store_true",
        help="Extract structured data from Archive Center minutes PDFs (Claude API required)",
    )
    parser.add_argument(
        "--batch-extract",
        action="store_true",
        help="Submit unextracted minutes as an Anthropic Batch API job (50%% discount)",
    )
    parser.add_argument(
        "--batch-status",
        metavar="BATCH_ID",
        help="Check status of a batch extraction job",
    )
    parser.add_argument(
        "--collect-batch",
        metavar="BATCH_ID",
        help="Collect results from a completed batch extraction job",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max documents to process per run. Re-run to continue.",
    )
    parser.add_argument(
        "--amid",
        type=int,
        default=None,
        help="Archive Center AMID to extract (overrides minutes_amid from config). "
             "Use with --extract-minutes for commission minutes.",
    )
    parser.add_argument(
        "--body-type",
        default="city_council",
        help="Body type for extraction prompt: city_council (default), commission, board, etc.",
    )
    parser.add_argument(
        "--enrich",
        action="store_true",
        help="After syncing, run all downstream enrichments from the pipeline manifest DAG",
    )
    parser.add_argument(
        "--enrich-only",
        action="store_true",
        help="Skip source sync — just run all enrichments that detect pending work",
    )
    args = parser.parse_args()

    if args.list_cities:
        for city in list_configured_cities():
            cfg = get_city_config(city["fips_code"])
            sources = ", ".join(cfg["data_sources"].keys())
            print(f"  {city['fips_code']}  {city['name']}, {city['state']}  [{sources}]")
        sys.exit(0)

    if args.backfill_layer2:
        print("Backfilling Layer 2 from existing eSCRIBE documents...")
        conn = get_connection()
        try:
            result = backfill_escribemeetings_layer2(conn, city_fips=args.city_fips)
            conn.commit()
            print(json.dumps(result, indent=2))
        finally:
            conn.close()
        sys.exit(0)

    if args.extract_minutes:
        amid_label = f" (AMID={args.amid})" if args.amid else ""
        print(f"Extracting structured data from Archive Center minutes{amid_label}...")
        conn = get_connection()
        try:
            result = sync_minutes_extraction(
                conn, city_fips=args.city_fips, sync_type=args.sync_type,
                limit=args.limit, amid=args.amid, body_type=args.body_type,
            )
            print(json.dumps(result, indent=2))
        finally:
            conn.close()
        sys.exit(0)

    if args.batch_extract:
        print("Submitting minutes extraction as Anthropic Batch API job...")
        conn = get_connection()
        try:
            result = submit_minutes_batch(
                conn, city_fips=args.city_fips, limit=args.limit,
            )
            print(json.dumps(result, indent=2))
        finally:
            conn.close()
        sys.exit(0)

    if args.batch_status:
        from pipeline import check_batch_status
        status = check_batch_status(args.batch_status)
        print(json.dumps(status, indent=2))
        sys.exit(0)

    if args.collect_batch:
        print(f"Collecting results from batch {args.collect_batch}...")
        conn = get_connection()
        try:
            result = collect_minutes_batch(
                conn, args.collect_batch, city_fips=args.city_fips,
            )
            print(json.dumps(result, indent=2))
        finally:
            conn.close()
        sys.exit(0)

    # ── Enrich-only mode: run all enrichments that detect pending work ──
    if args.enrich_only:
        enrichment_keys = [
            "topic_tagging", "summary_generation", "conflict_scanning",
            "meeting_summary_generation", "vote_explainer_generation",
            "theme_extraction", "orientation_generation", "recap_generation",
            "transcript_vote_extraction", "comment_summary_generation",
        ]
        print(f"\n{'=' * 60}")
        print(f"  ENRICHMENT SWEEP — running all enrichments with pending work")
        print(f"{'=' * 60}\n")
        any_failed = False
        skipped_budget = 0
        for name in enrichment_keys:
            print(f"── Enrichment: {name} ──")
            try:
                result = run_sync(
                    source=name,
                    city_fips=args.city_fips,
                    triggered_by=args.triggered_by,
                )
                new = result.get("result", {}).get("records_new", 0)
                if new:
                    print(f"  → {new} new records")
                if result.get("status") == "failed":
                    any_failed = True
                elif result.get("status") == "skipped":
                    # Budget lock/cap skip (P0.9) — counted separately so
                    # the sweep exits 0: the safety rails firing is not a
                    # code failure.
                    skipped_budget += 1
            except Exception as e:
                print(f"  ERROR: {e}")
                any_failed = True
        if skipped_budget:
            print(f"\n[skipped: budget lock/cap] {skipped_budget} enrichment(s) "
                  f"skipped by the Anthropic budget rails")
        if any_failed:
            sys.exit(1)
        sys.exit(0)

    if not args.source:
        parser.error("--source is required (unless using --list-cities, --enrich-only)")

    pipeline_run_id = args.pipeline_run_id or os.getenv("GITHUB_RUN_ID")

    result = run_sync(
        source=args.source,
        city_fips=args.city_fips,
        sync_type=args.sync_type,
        triggered_by=args.triggered_by,
        pipeline_run_id=pipeline_run_id,
        limit=args.limit,
        max_retries=args.max_retries,
    )

    print(f"\n::group::Sync Summary")
    print(json.dumps(result, indent=2, default=str))
    print(f"::endgroup::")

    if result.get("status") == "failed":
        sys.exit(1)

    # ── Post-sync enrichment: run downstream enrichments ──
    if args.enrich and result.get("status") != "failed":
        conn = get_connection()
        try:
            enrichment_results = run_downstream(
                source=args.source,
                conn=conn,
                city_fips=args.city_fips,
                triggered_by=args.triggered_by,
            )
            if enrichment_results:
                print(f"\n::group::Enrichment Summary")
                print(json.dumps(enrichment_results, indent=2, default=str))
                print(f"::endgroup::")
        finally:
            conn.close()


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    main()
