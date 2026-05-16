"""
archive_center pipeline module — extracted from data_sync.py (Phase 2.3).

Each sync_X function is registered in data_sync.SYNC_SOURCES and dispatched
by data_sync.run_sync. Module-level helpers (archive_center-specific) live alongside.
"""
from __future__ import annotations

import json
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


def sync_archive_center(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync documents from CivicPlus Archive Center.

    For incremental: downloads new docs from Tier 1-2 AMIDs since last sync.
    For full: re-enumerates all AMIDs and downloads Tier 1-2.
    """
    from archive_center_discovery import (
        create_session,
        enumerate_amids,
        _parse_document_list,
        download_document,
        extract_text,
        save_to_documents,
        get_download_tier,
        CIVICPLUS_BASE_URL,
        ARCHIVE_LISTING_URL,
        RAW_DIR,
    )

    session = create_session()
    modules = enumerate_amids(session)

    # Filter to Tier 1-2 AMIDs
    target_modules = {
        k: v for k, v in modules.items()
        if get_download_tier(k) <= 2
    }
    print(f"  Found {len(target_modules)} Tier 1-2 archive modules")

    all_docs = []
    for amid, info in sorted(target_modules.items()):
        url = f"{CIVICPLUS_BASE_URL}{ARCHIVE_LISTING_URL.format(amid=amid)}"
        resp = session.get(url, timeout=30)
        docs = _parse_document_list(resp.text)
        print(f"  AMID {amid} ({info['name'][:30]}): {len(docs)} docs")

        for doc in docs:
            doc["amid"] = amid
            doc["amid_name"] = info["name"]
            dest = RAW_DIR / f"AMID_{amid}"
            filepath = download_document(session, doc["adid"], dest)
            if filepath:
                doc["text"] = extract_text(filepath)
            all_docs.append(doc)

    print(f"  Saving {len(all_docs)} documents to Layer 1...")
    stats = save_to_documents(conn, all_docs, city_fips)

    # Counter Contract (Phase D-3b, 2026-05-16, audit B9): records_new
    # now reflects ACTUAL Layer 1 row inserts. Pre Phase D-3b, the
    # counter incremented on every ingest_document call regardless of
    # content_hash dedup hits, so re-runs reported full-archive-size
    # "new" counts. The last archive_center sync's records_new=3500
    # was almost entirely dedup hits — corrected here.
    return {
        "records_fetched": len(all_docs),
        "records_new": stats["inserted"],
        "records_deduplicated": stats["deduplicated"],
        "records_errors": stats["errors"],
        "records_updated": 0,
        "amids_scanned": len(target_modules),
    }



def sync_written_comments(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
    **kwargs,
) -> dict:
    """Extract written public comments from Archive Center PDFs and eSCRIBE eComments."""
    from written_comment_extractor import (
        _find_comment_documents,
        _find_meeting_by_date,
        _already_has_written_comments,
        import_written_comments,
        _process_ecomments,
        SOURCE_ARCHIVE,
    )

    docs = _find_comment_documents(conn, city_fips)
    total_inserted = 0
    total_docs = 0
    errors = 0

    for doc in docs:
        meeting_id = _find_meeting_by_date(conn, doc["meeting_date"], city_fips)
        if not meeting_id:
            continue

        if sync_type != "full":
            existing = _already_has_written_comments(conn, meeting_id)
            if existing > 0:
                continue

        try:
            stats = import_written_comments(
                meeting_id, doc["emails"], SOURCE_ARCHIVE, city_fips
            )
            total_inserted += stats["inserted"]
            total_docs += 1
        except Exception as e:
            print(f"  ERROR processing ADID {doc['adid']}: {e}")
            errors += 1

    # Also process eSCRIBE eComments
    _process_ecomments(city_fips=city_fips)

    return {
        "records_fetched": len(docs),
        "records_new": total_inserted,
        "records_updated": 0,
        "documents_processed": total_docs,
        "errors": errors,
    }


