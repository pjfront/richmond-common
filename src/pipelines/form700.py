"""
form700 pipeline module — extracted from data_sync.py (Phase 2.3).

Each sync_X function is registered in data_sync.SYNC_SOURCES and dispatched
by data_sync.run_sync. Module-level helpers (form700-specific) live alongside.
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


def sync_form700(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
    department: str | None = None,
) -> dict:
    """Sync Form 700 filings from the NetFile SEI public-portal JSON API.

    Reads from form700_netfile_api structured schedule transactions (the
    source-closest artifact). Does NOT read from filing PDFs or Claude
    extraction — the old WebForms portal was decommissioned ~2026-06 and the
    API's line items are the filer's own structured entries (confidence 1.0,
    zero LLM cost). Raw per-filing JSON is preserved in the Document Lake.

    For incremental: only loads filings not already in form700_filings.
    For full: re-loads all discovered filings (upsert + interest replace).
    `department` scopes discovery (e.g. "City Council") for targeted
    catch-up runs; the scheduled sync passes None (whole agency).
    """
    from form700_netfile_api import fetch_filing_records, PORTAL_URL
    from db import load_form700_to_db, ingest_document

    print("  Discovering Form 700 filings from NetFile SEI API...")
    records = fetch_filing_records(department=department)
    print(f"  Found {len(records)} operative filings"
          + (f" (department={department})" if department else ""))

    # Filter to unprocessed filings (incremental mode)
    if sync_type == "incremental":
        with conn.cursor() as cur:
            cur.execute(
                """SELECT filer_name, filing_year, statement_type, source
                   FROM form700_filings WHERE city_fips = %s""",
                (city_fips,),
            )
            existing = {
                (row[0], row[1], row[2], row[3]) for row in cur.fetchall()
            }

        new_records = []
        for rec in records:
            meta = rec["filing_metadata"]
            key = (
                meta.get("filer_name", ""),
                meta.get("filing_year", 0),
                meta.get("statement_type", "annual"),
                "netfile_sei",
            )
            if key not in existing:
                new_records.append(rec)

        print(f"  {len(new_records)} new filings to process (skipping {len(records) - len(new_records)} existing)")
        records = new_records

    if not records:
        return {
            "records_fetched": 0,
            "records_new": 0,
            "records_updated": 0,
            "filings_discovered": 0,
        }

    filings_processed = 0
    interests_total = 0
    errors = 0

    for rec in records:
        meta = rec["filing_metadata"]
        filer_name = meta.get("filer_name", "Unknown")
        filing_year = meta.get("filing_year", 0)
        print(f"  Processing: {filer_name} ({filing_year} {meta.get('statement_type')})...")

        try:
            # Preserve the raw API JSON in the Document Lake (re-extractable)
            doc_id = None
            try:
                raw_bytes = json.dumps(rec["raw"], default=str).encode("utf-8")
                filing_id = (rec["raw"].get("filing") or {}).get("filingId", "")
                doc_id = ingest_document(
                    conn,
                    city_fips=city_fips,
                    source_type="form700",
                    raw_content=raw_bytes,
                    credibility_tier=1,
                    source_url=PORTAL_URL,
                    source_identifier=f"form700_api_{filing_id or filer_name}_{filing_year}",
                    mime_type="application/json",
                    metadata={
                        "filer_name": filer_name,
                        "filing_year": filing_year,
                        "statement_type": meta.get("statement_type", "annual"),
                        "netfile_filing_id": filing_id,
                        "pipeline": "data_sync.form700",
                    },
                )
            except Exception as e:
                print(f"    WARNING: Document storage failed: {e}")

            meta["document_id"] = doc_id
            result = load_form700_to_db(conn, rec["extraction"], meta, city_fips=city_fips)

            filings_processed += 1
            interests_total += result["interests_count"]

            matched = "matched" if result["matched_official"] else "unmatched"
            print(f"    Loaded: {result['interests_count']} interests ({matched})")

        except Exception as e:
            print(f"    ERROR processing {filer_name}: {e}")
            errors += 1

    return {
        "records_fetched": len(records),
        "records_new": filings_processed,
        "records_updated": 0,
        "filings_discovered": len(records),
        "interests_loaded": interests_total,
        "errors": errors,
    }


