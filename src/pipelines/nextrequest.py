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


def sync_nextrequest(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
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

    print("  Fetching from NextRequest client API...")
    since_date = None
    authoritative_listing_due = sync_type == "full"
    if sync_type == "incremental":
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
            last_authoritative = full_row[0] if full_row and full_row[0] else None
            if last_authoritative is None:
                authoritative_listing_due = True
            else:
                now = datetime.now(tz=last_authoritative.tzinfo)
                authoritative_listing_due = (
                    now - last_authoritative
                    >= timedelta(hours=NEXTREQUEST_AUTHORITATIVE_INTERVAL_HOURS)
                )

    if authoritative_listing_due:
        # A daily complete public listing is the proof boundary for removals.
        # Detail/document bodies remain bounded below; this phase is list-only.
        since_date = None

    # Authoritative removal scans are list-only; ordinary incrementals fetch
    # detail for recent rows to apply mutable field/status amendments.
    skip_details = authoritative_listing_due

    results = scrape_all(
        since_date=since_date,
        download_docs=False,
        extract_text=False,
        city_fips=city_fips,
        skip_details=skip_details,
        include_documents=not skip_details,
    )

    # Submitted-date pagination cannot see an old request that just closed or
    # received response documents. The public newest-document index identifies
    # affected old requests directly, while a bounded oldest-first rotation of
    # locally open requests catches status/closure changes with fixed API cost.
    base_reconciled_ids = {
        str(request.get("request_number"))
        for request in results.get("requests", [])
        if request.get("request_number")
        and not set(request.get("_incomplete_stages") or []).intersection({
            "detail", "documents", "documents_not_requested",
        })
    }
    index_failures = []
    if results.get("request_listing_complete") is True:
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
            results["public_document_listing_complete"] = False
            index_failures.append({
                "request_id": "public-documents-full-index",
                "stage": "documents_index_full",
                "error": f"{type(exc).__name__}: {exc}"[:500],
            })
    try:
        recent_document_ids = list_recent_document_request_ids(
            city_fips=city_fips,
            limit=NEXTREQUEST_RECENT_DOCUMENT_LIMIT,
        )
    except Exception as exc:
        recent_document_ids = []
        index_failures.append({
            "request_id": "public-documents-index",
            "stage": "documents_index",
            "error": f"{type(exc).__name__}: {exc}"[:500],
        })

    targeted_ids = list(dict.fromkeys(
        request_id
        for request_id in recent_document_ids
        if request_id not in base_reconciled_ids
    ))
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
    reconciliation["stats"].setdefault("failures", []).extend(index_failures)
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
        "retryable_incomplete": failure_count > 0,
        "incomplete_count": failure_count,
        "incomplete_reasons": (
            [f"{failure_count} NextRequest detail/timeline/document fetch(es) failed"]
            + failure_details
            if failure_count
            else []
        ),
    }


