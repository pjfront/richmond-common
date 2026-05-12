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
) -> dict:
    """Sync Form 700 filings from NetFile SEI portal.

    Pipeline: discover filings → download PDFs → extract text →
    Claude API extraction → load to database.

    For incremental: only processes filings not already in form700_filings.
    For full: re-processes all discovered filings.
    """
    import asyncio
    from form700_scraper import discover_filings, download_filing_pdf
    from form700_extractor import (
        extract_text_from_pdf,
        extract_form700,
        match_filer_to_official,
    )
    from db import load_form700_to_db, ingest_document

    output_dir = Path(__file__).parent / "data" / "form700"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Discover filings from NetFile SEI portal
    print("  Discovering Form 700 filings from NetFile SEI...")

    filings = asyncio.run(discover_filings(city_fips=city_fips))
    print(f"  Found {len(filings)} filings on portal")

    # 2. Filter to unprocessed filings (incremental mode)
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

        new_filings = []
        for f in filings:
            key = (
                f.get("filer_name", ""),
                f.get("filing_year", 0),
                f.get("statement_type", "annual"),
                "netfile_sei",
            )
            if key not in existing:
                new_filings.append(f)

        print(f"  {len(new_filings)} new filings to process (skipping {len(filings) - len(new_filings)} existing)")
        filings = new_filings

    if not filings:
        return {
            "records_fetched": 0,
            "records_new": 0,
            "records_updated": 0,
            "filings_discovered": 0,
        }

    # 3. Download PDFs, extract, and load
    filings_processed = 0
    interests_total = 0
    errors = 0

    for filing in filings:
        filer_name = filing.get("filer_name", "Unknown")
        filing_year = filing.get("filing_year", 0)
        detail_url = filing.get("detail_url", "")

        if not detail_url:
            print(f"  SKIP {filer_name} ({filing_year}): no PDF URL")
            errors += 1
            continue

        print(f"  Processing: {filer_name} ({filing_year})...")

        try:
            # Download PDF (async function, needs asyncio.run)
            pdf_path = asyncio.run(download_filing_pdf(
                detail_url,
                dest_dir=output_dir,
                filer_name=filer_name,
                filing_year=filing_year,
            ))
            if not pdf_path:
                print(f"    ERROR: Download failed for {filer_name}")
                errors += 1
                continue

            # Store raw PDF in Document Lake
            doc_id = None
            try:
                raw_bytes = Path(pdf_path).read_bytes()
                doc_id = ingest_document(
                    conn,
                    city_fips=city_fips,
                    source_type="form700",
                    raw_content=raw_bytes,
                    credibility_tier=1,
                    source_url=detail_url,
                    source_identifier=f"form700_{filer_name}_{filing_year}",
                    mime_type="application/pdf",
                    metadata={
                        "filer_name": filer_name,
                        "department": filing.get("department"),
                        "position": filing.get("position"),
                        "filing_year": filing_year,
                        "statement_type": filing.get("statement_type", "annual"),
                        "pipeline": "data_sync.form700",
                    },
                )
            except Exception as e:
                print(f"    WARNING: Document storage failed: {e}")

            # Extract text from PDF
            pdf_text = extract_text_from_pdf(Path(pdf_path))
            if not pdf_text.strip():
                print(f"    SKIP: Empty PDF text for {filer_name}")
                errors += 1
                continue

            # Claude API extraction
            extraction = extract_form700(
                pdf_text,
                filer_name=filer_name,
                agency=filing.get("department", ""),
                filing_year=filing_year,
                statement_type=filing.get("statement_type", "annual"),
            )

            confidence = extraction.get("extraction_confidence", 0)
            n_interests = len(extraction.get("interests", []))
            print(f"    Extracted: {n_interests} interests (confidence: {confidence:.2f})")

            # Load to database
            result = load_form700_to_db(
                conn,
                extraction,
                filing_metadata={
                    "filer_name": filer_name,
                    "agency": filing.get("department", ""),
                    "position": filing.get("position", ""),
                    "statement_type": filing.get("statement_type", "annual"),
                    "filing_year": filing_year,
                    "source": "netfile_sei",
                    "source_url": detail_url,
                    "document_id": doc_id,
                },
                city_fips=city_fips,
            )

            filings_processed += 1
            interests_total += result["interests_count"]

            matched = "matched" if result["matched_official"] else "unmatched"
            print(f"    Loaded: {result['interests_count']} interests ({matched})")

        except Exception as e:
            print(f"    ERROR processing {filer_name}: {e}")
            errors += 1

    return {
        "records_fetched": len(filings),
        "records_new": filings_processed,
        "records_updated": 0,
        "filings_discovered": len(filings),
        "interests_loaded": interests_total,
        "errors": errors,
    }


# Content-based detection for minutes vs comment compilations.
# The city sometimes publishes public comments first, then replaces the PDF
# with combined minutes+comments. Hardcoded ADID lists don't scale —
# detect by checking raw_text for structural markers of actual minutes.
_MINUTES_MARKERS = ("ROLL CALL", "called to order", "ADJOURNMENT")


