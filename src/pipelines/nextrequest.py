"""
nextrequest pipeline module — extracted from data_sync.py (Phase 2.3).

Each sync_X function is registered in data_sync.SYNC_SOURCES and dispatched
by data_sync.run_sync. Module-level helpers (nextrequest-specific) live alongside.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
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
NEXTREQUEST_OPEN_RECONCILE_LIMIT = 25
NEXTREQUEST_RECENT_DOCUMENT_LIMIT = 50
NEXTREQUEST_AUTHORITATIVE_INTERVAL_HOURS = 24
NEXTREQUEST_DETECTOR_LOOKBACK_DAYS = 14
NEXTREQUEST_DETECTOR_DETAIL_LIMIT = 5
NEXTREQUEST_DETECTOR_DOCUMENT_LIMIT = 5
NEXTREQUEST_RETRY_SCOPE_LIMIT = 100
NEXTREQUEST_RETRY_ATTEMPT_LIMIT = 5


def _select_open_reconciliation_ids(
    conn,
    city_fips: str,
    *,
    exclude: set[str],
    limit: int = NEXTREQUEST_OPEN_RECONCILE_LIMIT,
) -> list[str]:
    """Rotate through all current local requests independent of submit date.

    ``updated_at`` advances only after a complete detail/timeline/document
    reconciliation. Partial rows therefore remain at the front of this
    durable database-backed queue instead of disappearing behind a cursor.
    Closed rows are intentionally included: old response documents can later
    be retracted/private even after the request closes.
    """
    if limit <= 0:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """SELECT request_number
               FROM nextrequest_requests
               WHERE city_fips = %s
                 AND source_removed_at IS NULL
                 AND NOT (request_number = ANY(%s))
               ORDER BY updated_at ASC NULLS FIRST, request_number ASC
               LIMIT %s""",
            (city_fips, sorted(exclude), limit),
        )
        return [str(row[0]) for row in cur.fetchall() if row and row[0]]


def _merge_scrape_results(base: dict, reconciliation: dict) -> dict:
    """Merge targeted results/failures into the submit-date scrape."""
    merged = dict(base)
    by_request = {
        request.get("request_number"): request
        for request in base.get("requests", [])
        if request.get("request_number")
    }
    order = list(by_request)
    for request in reconciliation.get("requests", []):
        request_number = request.get("request_number")
        if not request_number:
            continue
        if request_number not in by_request:
            order.append(request_number)
        by_request[request_number] = request
    merged["requests"] = [by_request[number] for number in order]

    base_stats = dict(base.get("stats") or {})
    reconcile_stats = reconciliation.get("stats") or {}
    failures = list(base_stats.get("failures") or [])
    failures.extend(reconcile_stats.get("failures") or [])
    failed_request_ids = sorted({
        str(failure.get("request_id"))
        for failure in failures
        if failure.get("request_id")
    })
    failure_counts = {}
    for failure in failures:
        stage = str(failure.get("stage") or "unknown")
        failure_counts[stage] = failure_counts.get(stage, 0) + 1
    base_stats.update({
        "total_found": len(merged["requests"]),
        "details_scraped": sum(
            1
            for request in merged["requests"]
            if "detail" not in set(request.get("_incomplete_stages") or [])
        ),
        "documents_found": sum(
            len(request.get("documents", []))
            for request in merged["requests"]
        ),
        "failure_count": len(failures),
        "failed_request_ids": failed_request_ids,
        "failure_counts": failure_counts,
        "failures": failures,
    })
    merged["stats"] = base_stats
    return merged


def _bounded_retry_request_ids(request_ids: list[str] | None) -> list[str]:
    """Validate a persisted NextRequest retry scope before portal access.

    Synthetic failure identities such as ``public-documents-full-index`` are
    deliberately excluded: the daily scheduled reconciliation owns global
    deletion proof. Detector retries only own concrete request IDs already
    recorded in the failed sync artifact.
    """
    bounded = []
    seen = set()
    for value in request_ids or []:
        request_id = str(value).strip()
        parts = request_id.split("-", 1)
        if (
            len(parts) != 2
            or not parts[0].isdigit()
            or not parts[1].isdigit()
            or request_id in seen
        ):
            continue
        seen.add(request_id)
        bounded.append(request_id)
    if request_ids is not None and not bounded:
        raise RuntimeError(
            "NextRequest retry artifact contains no concrete request IDs; "
            "manual reconciliation is required"
        )
    if len(bounded) > NEXTREQUEST_RETRY_SCOPE_LIMIT:
        raise RuntimeError(
            "NextRequest persisted retry scope exceeds the 100-request safety "
            "bound; manual reconciliation is required"
        )
    return bounded


def _append_deferred_failures(
    results: dict,
    request_ids: list[str],
    *,
    stage: str,
    reason: str,
) -> None:
    """Keep unattempted request IDs in the durable retry artifact."""
    if not request_ids:
        return
    stats = results.setdefault("stats", {})
    failures = list(stats.get("failures") or [])
    failures.extend(
        {
            "request_id": request_id,
            "stage": stage,
            "error": reason,
        }
        for request_id in request_ids
    )
    stats["failures"] = failures
    stats["failure_count"] = len(failures)
    stats["failed_request_ids"] = sorted({
        str(failure.get("request_id"))
        for failure in failures
        if failure.get("request_id")
    })
    failure_counts: dict[str, int] = {}
    for failure in failures:
        failure_stage = str(failure.get("stage") or "unknown")
        failure_counts[failure_stage] = failure_counts.get(failure_stage, 0) + 1
    stats["failure_counts"] = failure_counts


def _is_rate_limit_error(exc: BaseException) -> bool:
    """Return whether a portal exception is an HTTP 429."""
    return getattr(getattr(exc, "response", None), "status_code", None) == 429


def _has_rate_limit_failure(results: dict) -> bool:
    """Return whether an earlier scrape phase already hit the portal limit."""
    return any(
        failure.get("stage") == "rate_limit"
        for failure in (results.get("stats", {}).get("failures") or [])
        if isinstance(failure, dict)
    )


def sync_nextrequest(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
    detector_event: bool = False,
    retry_request_ids: list[str] | None = None,
) -> dict:
    """Sync CPRA requests from NextRequest portal.

    Uses NextRequest's public client JSON API (no Playwright needed).
    For incremental: fetches requests since last sync.
    For full: fetches all requests with skip_details for speed.
    """
    from nextrequest_scraper import (
        list_recent_document_request_ids,
        save_to_db,
        scrape_all,
        scrape_request_ids,
    )

    retry_scope = (
        _bounded_retry_request_ids(retry_request_ids)
        if retry_request_ids is not None
        else None
    )
    print("  Fetching from NextRequest client API...")
    if retry_scope is not None:
        retry_attempt_scope = retry_scope[:NEXTREQUEST_RETRY_ATTEMPT_LIMIT]
        deferred_retry_scope = retry_scope[NEXTREQUEST_RETRY_ATTEMPT_LIMIT:]
        print(
            "::notice title=NextRequest bounded retry::"
            f"Retrying {len(retry_attempt_scope)} of {len(retry_scope)} "
            "persisted request(s); broad listing and reconciliation are "
            "disabled"
        )
    else:
        retry_attempt_scope = None
        deferred_retry_scope = []

    since_date = None
    authoritative_listing_due = sync_type == "full" and not detector_event
    if sync_type == "incremental" and retry_scope is None:
        # Find last successful sync date
        with conn.cursor() as cur:
            cur.execute(
                """SELECT MAX(completed_at) FROM data_sync_log
                   WHERE source = 'nextrequest' AND status = 'completed'
                     AND city_fips = %s
                     AND NOT (
                       COALESCE(metadata, '{}'::jsonb)
                       @> '{"retryable_incomplete": true}'::jsonb
                     )""",
                (city_fips,),
            )
            row = cur.fetchone()
            if row and row[0]:
                since_date = row[0].strftime("%Y-%m-%d")

            if not detector_event:
                cur.execute(
                    """SELECT MAX(completed_at) FROM data_sync_log
                       WHERE source = 'nextrequest' AND status = 'completed'
                         AND city_fips = %s
                         AND COALESCE(metadata, '{}'::jsonb)
                           @> '{"request_listing_complete": true}'::jsonb
                         AND COALESCE(metadata, '{}'::jsonb)
                           @> '{"public_document_listing_complete": true}'::jsonb""",
                    (city_fips,),
                )
                full_row = cur.fetchone()
                last_authoritative = (
                    full_row[0] if full_row and full_row[0] else None
                )
                if last_authoritative is None:
                    authoritative_listing_due = True
                else:
                    now = datetime.now(tz=last_authoritative.tzinfo)
                    authoritative_listing_due = (
                        now - last_authoritative
                        >= timedelta(
                            hours=NEXTREQUEST_AUTHORITATIVE_INTERVAL_HOURS
                        )
                    )

        # A detector event is a near-live bounded slice, never the daily
        # authoritative sweep. If there is no prior clean cursor, use a fixed
        # lookback instead of replaying every historical request.
        if detector_event:
            detector_cutoff = (
                datetime.now() - timedelta(
                    days=NEXTREQUEST_DETECTOR_LOOKBACK_DAYS
                )
            ).strftime("%Y-%m-%d")
            if since_date is None or since_date < detector_cutoff:
                since_date = detector_cutoff

    if authoritative_listing_due:
        # A daily complete public listing is the proof boundary for removals.
        # Detail/document bodies remain bounded below; this phase is list-only.
        since_date = None

    # Authoritative removal scans are list-only; ordinary incrementals fetch
    # detail for recent rows to apply mutable field/status amendments.
    skip_details = authoritative_listing_due

    if retry_attempt_scope is not None:
        results = scrape_request_ids(
            retry_attempt_scope,
            city_fips=city_fips,
            include_documents=True,
        )
        _append_deferred_failures(
            results,
            deferred_retry_scope,
            stage="retry_slice_deferred",
            reason=(
                "Deferred without portal access by the five-request "
                "detector retry limit"
            ),
        )
        # A targeted retry can update only named rows. It must never provide
        # evidence for global request/document tombstones.
        results["request_listing_complete"] = False
        results["public_document_listing_complete"] = False
    else:
        results = scrape_all(
            since_date=since_date,
            download_docs=False,
            extract_text=False,
            city_fips=city_fips,
            skip_details=skip_details,
            include_documents=not skip_details,
            detail_limit=(
                NEXTREQUEST_DETECTOR_DETAIL_LIMIT
                if detector_event
                else None
            ),
        )

    # Submitted-date pagination cannot see an old request that just closed or
    # received response documents. The public newest-document index identifies
    # affected old requests directly, while a bounded oldest-first rotation of
    # locally open requests catches status/closure changes with fixed API cost.
    if retry_scope is None:
        base_reconciled_ids = {
            str(request.get("request_number"))
            for request in results.get("requests", [])
            if request.get("request_number")
            and not set(request.get("_incomplete_stages") or []).intersection({
                "detail", "documents", "documents_not_requested",
            })
        }
        index_failures = []
        portal_rate_limited = _has_rate_limit_failure(results)
        if (
            not portal_rate_limited
            and results.get("request_listing_complete") is True
        ):
            try:
                from nextrequest_scraper import list_all_public_document_ids

                all_public_document_ids = list_all_public_document_ids(
                    city_fips=city_fips,
                )
                results["public_document_listing_complete"] = True
                results["authoritative_public_document_ids"] = (
                    all_public_document_ids
                )
            except Exception as exc:
                portal_rate_limited = _is_rate_limit_error(exc)
                results["public_document_listing_complete"] = False
                index_failures.append({
                    "request_id": "public-documents-full-index",
                    "stage": "documents_index_full",
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                })
        try:
            recent_document_ids = (
                []
                if portal_rate_limited
                else list_recent_document_request_ids(
                    city_fips=city_fips,
                    limit=(
                        NEXTREQUEST_DETECTOR_DOCUMENT_LIMIT
                        if detector_event
                        else NEXTREQUEST_RECENT_DOCUMENT_LIMIT
                    ),
                )
            )
        except Exception as exc:
            recent_document_ids = []
            portal_rate_limited = _is_rate_limit_error(exc)
            index_failures.append({
                "request_id": "public-documents-index",
                "stage": "documents_index",
                "error": f"{type(exc).__name__}: {exc}"[:500],
            })

        targeted_ids = (
            []
            if portal_rate_limited
            else list(dict.fromkeys(
                request_id
                for request_id in recent_document_ids
                if request_id not in base_reconciled_ids
            ))
        )
        if not detector_event and not portal_rate_limited:
            targeted_ids.extend(
                _select_open_reconciliation_ids(
                    conn,
                    city_fips,
                    exclude=base_reconciled_ids | set(targeted_ids),
                )
            )
        if targeted_ids:
            reconciliation = scrape_request_ids(
                targeted_ids,
                city_fips=city_fips,
                include_documents=True,
            )
        else:
            reconciliation = {
                "requests": [],
                "stats": {"failures": []},
            }
        reconciliation["stats"].setdefault("failures", []).extend(
            index_failures
        )
        results = _merge_scrape_results(results, reconciliation)

    print(f"  Fetched {results['stats']['total_found']} requests"
          + (f", {results['stats']['details_scraped']} with details"
             if results['stats']['details_scraped'] > 0 else ""))

    print("  Saving to database...")
    stats = save_to_db(conn, results, city_fips)
    scrape_stats = results.get("stats", {})
    failure_count = int(scrape_stats.get("failure_count") or 0)
    failures = scrape_stats.get("failures") or []
    failed_request_ids = scrape_stats.get("failed_request_ids") or []
    failure_details = [
        f"{failure.get('request_id', 'unknown')} "
        f"{failure.get('stage', 'unknown')}: {failure.get('error', 'failed')}"
        for failure in failures[:4]
    ]

    # Counter Contract (Phase D-3, 2026-05-16): records_new now means
    # ACTUAL newly-inserted requests via RETURNING (xmax = 0), not
    # "ON CONFLICT DO UPDATE statements that ran." Previously records_new
    # = stats["requests_saved"] which counted every upsert regardless
    # of whether it actually inserted (audit B10).
    return {
        "records_fetched": results["stats"]["total_found"],
        "records_new": stats["requests_inserted"],
        "records_updated": stats["requests_updated"],
        "documents_inserted": stats["documents_inserted"],
        "documents_skipped_existing": stats["documents_skipped_existing"],
        "documents_tombstoned": stats.get("documents_tombstoned", 0),
        "requests_tombstoned": stats.get("requests_tombstoned", 0),
        "request_listing_complete": bool(
            results.get("request_listing_complete")
        ),
        "public_document_listing_complete": bool(
            results.get("public_document_listing_complete")
        ),
        "scrape_failures": failure_count,
        "failed_request_ids": failed_request_ids,
        "retry_scope_applied": retry_scope is not None,
        "retry_scope_size": len(retry_scope or []),
        "retry_attempt_size": len(retry_attempt_scope or []),
        "retry_deferred_size": len(deferred_retry_scope),
        "retryable_incomplete": failure_count > 0,
        "incomplete_count": failure_count,
        "incomplete_reasons": (
            [f"{failure_count} NextRequest detail/timeline/document fetch(es) failed"]
            + failure_details
            if failure_count
            else []
        ),
    }


