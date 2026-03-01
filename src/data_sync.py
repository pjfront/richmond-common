"""
Richmond Transparency Project — Unified Data Source Sync

Syncs external data sources to Supabase with logging and observability.
Each sync creates a data_sync_log entry for tracking freshness.

Supported sources:
  - netfile: Local campaign contributions (NetFile Connect2 API)
  - calaccess: State PAC/IE contributions (CAL-ACCESS bulk download)
  - escribemeetings: Meeting agendas and documents
  - nextrequest: CPRA public records requests (NextRequest portal)
  - archive_center: CivicPlus Archive Center documents (resolutions, ordinances, etc.)
  - form700: Form 700 financial disclosures (NetFile SEI portal)

Usage:
  python data_sync.py --source netfile
  python data_sync.py --source calaccess
  python data_sync.py --source netfile --triggered-by n8n
  python data_sync.py --source netfile --sync-type full
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from city_config import get_city_config, list_configured_cities
from db import (
    get_connection,
    create_sync_log,
    complete_sync_log,
    load_contributions_to_db,
)

DEFAULT_FIPS = "0660620"  # Richmond — keep as CLI default for backward compat


def sync_netfile(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync contributions from NetFile Connect2 API to Supabase.

    For incremental syncs, checks for new contributions since the last sync.
    For full syncs, downloads all contributions.
    """
    from netfile_client import (
        fetch_all_transactions,
        normalize_transaction,
        deduplicate_contributions,
    )

    # Fetch monetary (F460A=0) and non-monetary (F460C=1) contributions
    # Type 20 (F497P1 late contributions) is intermittently broken on NetFile API
    CONTRIBUTION_TYPES = [0, 1]

    print("  Fetching contributions from NetFile API...")
    all_transactions = []
    for type_id in CONTRIBUTION_TYPES:
        txs = fetch_all_transactions(transaction_type=type_id)
        all_transactions.extend(txs)

    # Normalize and deduplicate (same pipeline as netfile_client.py main)
    contributions = [normalize_transaction(tx) for tx in all_transactions]
    contributions = deduplicate_contributions(contributions)
    contributions = [c for c in contributions if c["amount"] != 0]
    print(f"  Fetched {len(contributions):,} contribution records")

    print("  Loading into database...")
    stats = load_contributions_to_db(conn, contributions, city_fips=city_fips)

    return {
        "records_fetched": len(contributions),
        "records_new": stats["contributions"],
        "records_updated": 0,
        "donors_created": stats["donors"],
        "committees_created": stats["committees"],
        "skipped": stats["skipped"],
    }


def sync_calaccess(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync contributions from CAL-ACCESS bulk data to Supabase.

    Downloads the full bulk ZIP (~1.5GB) and processes Richmond-related
    contributions. This is a heavy operation — run monthly.
    """
    from calaccess_client import (
        download_bulk_data,
        find_richmond_filers,
        find_richmond_filing_ids,
        get_richmond_contributions,
    )

    print("  Downloading CAL-ACCESS bulk ZIP (uses cache if available)...")
    zip_path = download_bulk_data(force=(sync_type == "full"))
    print(f"  ZIP at {zip_path}")

    print("  Finding Richmond filers...")
    filers = find_richmond_filers(zip_path)
    print(f"  Found {len(filers)} Richmond-area filers")

    print("  Finding Richmond filing IDs...")
    filing_map = find_richmond_filing_ids(zip_path)

    print("  Extracting contributions...")
    contributions = get_richmond_contributions(zip_path, filing_map=filing_map)
    print(f"  Found {len(contributions):,} contributions")

    print("  Loading into database...")
    stats = load_contributions_to_db(conn, contributions, city_fips=city_fips)

    return {
        "records_fetched": len(contributions),
        "records_new": stats["contributions"],
        "records_updated": 0,
        "donors_created": stats["donors"],
        "committees_created": stats["committees"],
        "skipped": stats["skipped"],
    }


def sync_escribemeetings(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Check eSCRIBE for upcoming meetings and scrape new agenda packets.

    For incremental: only checks upcoming meetings in the next 14 days.
    For full: scans the full date range (2020-present).
    """
    from escribemeetings_scraper import (
        create_session,
        discover_meetings,
        scrape_meeting,
    )
    from db import ingest_document

    session = create_session()

    if sync_type == "full":
        print("  Discovering all meetings from eSCRIBE...")
        meetings = discover_meetings(session)
    else:
        print("  Checking eSCRIBE for upcoming meetings...")
        meetings = discover_meetings(session)
        # Filter to upcoming 14 days
        from datetime import timedelta
        today = datetime.now().date()
        cutoff = today + timedelta(days=14)
        meetings = [
            m for m in meetings
            if m.get("meeting_date") and today <= datetime.strptime(m["meeting_date"], "%Y-%m-%d").date() <= cutoff
        ]

    print(f"  Found {len(meetings)} meetings to process")

    new_count = 0
    for meeting in meetings:
        meeting_date = meeting.get("meeting_date", "unknown")
        # Check if we already have this meeting's raw data
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id FROM documents
                   WHERE city_fips = %s AND source_type = 'escribemeetings'
                     AND source_identifier = %s""",
                (city_fips, f"escribemeetings_{meeting_date}"),
            )
            if cur.fetchone():
                continue  # Already have this meeting

        print(f"  Scraping {meeting_date}...")
        try:
            data = scrape_meeting(session, meeting)
            raw_bytes = json.dumps(data, indent=2).encode("utf-8")
            ingest_document(
                conn,
                city_fips=city_fips,
                source_type="escribemeetings",
                raw_content=raw_bytes,
                credibility_tier=1,
                source_url=data.get("meeting_url"),
                source_identifier=f"escribemeetings_{meeting_date}",
                mime_type="application/json",
                metadata={
                    "meeting_date": meeting_date,
                    "meeting_name": data.get("meeting_name"),
                    "item_count": len(data.get("items", [])),
                    "pipeline": "data_sync",
                },
            )
            new_count += 1
        except Exception as e:
            print(f"  ERROR scraping {meeting_date}: {e}")

    return {
        "records_fetched": len(meetings),
        "records_new": new_count,
        "records_updated": 0,
    }


def sync_nextrequest(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync CPRA requests from NextRequest portal.

    For incremental: scrapes requests updated since last sync.
    For full: re-scrapes all requests.
    """
    import asyncio
    from nextrequest_scraper import scrape_all, save_to_db

    print("  Scraping NextRequest portal...")
    since_date = None
    if sync_type == "incremental":
        # Find last successful sync date
        with conn.cursor() as cur:
            cur.execute(
                """SELECT MAX(completed_at) FROM data_sync_log
                   WHERE source = 'nextrequest' AND status = 'completed'
                     AND city_fips = %s""",
                (city_fips,),
            )
            row = cur.fetchone()
            if row and row[0]:
                since_date = row[0].strftime("%Y-%m-%d")

    results = asyncio.run(scrape_all(
        since_date=since_date,
        download_docs=True,
        extract_text=True,
    ))

    print(f"  Scraped {results['stats']['details_scraped']} requests, "
          f"{results['stats']['documents_found']} documents")

    print("  Saving to database...")
    stats = save_to_db(conn, results, city_fips)

    return {
        "records_fetched": results["stats"]["total_found"],
        "records_new": stats["requests_saved"],
        "records_updated": 0,
        "documents_saved": stats["documents_saved"],
    }


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
        ARCHIVE_MODULE_URL,
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
        url = f"{CIVICPLUS_BASE_URL}{ARCHIVE_MODULE_URL.format(amid=amid)}"
        resp = session.get(url, timeout=15)
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

    return {
        "records_fetched": len(all_docs),
        "records_new": stats["saved"],
        "records_updated": 0,
        "amids_scanned": len(target_modules),
    }


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


SYNC_SOURCES = {
    "netfile": sync_netfile,
    "calaccess": sync_calaccess,
    "escribemeetings": sync_escribemeetings,
    "nextrequest": sync_nextrequest,
    "archive_center": sync_archive_center,
    "form700": sync_form700,
}


def run_sync(
    source: str,
    city_fips: str = DEFAULT_FIPS,
    sync_type: str = "incremental",
    triggered_by: str = "manual",
    pipeline_run_id: str = None,
) -> dict:
    """Run a data sync for the specified source.

    Creates a data_sync_log entry, runs the sync, and updates the log.
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

    try:
        sync_fn = SYNC_SOURCES[source]
        result = sync_fn(conn, city_fips, sync_type, sync_log_id)

        execution_time = time.time() - start_time
        complete_sync_log(
            conn,
            sync_log_id=sync_log_id,
            records_fetched=result.get("records_fetched"),
            records_new=result.get("records_new"),
            records_updated=result.get("records_updated"),
            metadata={"execution_seconds": round(execution_time, 2), **result},
        )

        print(f"\n{'='*60}")
        print(f"Sync complete: {source}")
        print(f"  Fetched: {result.get('records_fetched', 0)}")
        print(f"  New: {result.get('records_new', 0)}")
        print(f"  Time: {execution_time:.1f}s")
        print(f"{'='*60}")

        return {"sync_log_id": str(sync_log_id), "status": "completed", **result}

    except Exception as e:
        execution_time = time.time() - start_time
        print(f"\nERROR: Sync failed after {execution_time:.1f}s: {e}")
        complete_sync_log(
            conn,
            sync_log_id=sync_log_id,
            error_message=str(e),
        )
        return {"sync_log_id": str(sync_log_id), "status": "failed", "error": str(e)}
    finally:
        conn.close()


# ── CLI ──────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Richmond Transparency Project — Data Source Sync",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Available sources: {', '.join(SYNC_SOURCES)}

Examples:
  python data_sync.py --source netfile
  python data_sync.py --source calaccess --sync-type full
  python data_sync.py --source escribemeetings --triggered-by n8n
        """,
    )
    parser.add_argument("--source", choices=list(SYNC_SOURCES), help="Data source to sync")
    parser.add_argument("--sync-type", choices=["full", "incremental"], default="incremental", help="Sync type")
    parser.add_argument("--triggered-by", default="manual", help="What triggered this sync")
    parser.add_argument("--city-fips", default=DEFAULT_FIPS, help="City FIPS code")
    parser.add_argument("--pipeline-run-id", help="GitHub Actions run ID or n8n execution ID")
    parser.add_argument("--list-cities", action="store_true", help="List configured cities and exit")
    args = parser.parse_args()

    if args.list_cities:
        for city in list_configured_cities():
            cfg = get_city_config(city["fips_code"])
            sources = ", ".join(cfg["data_sources"].keys())
            print(f"  {city['fips_code']}  {city['name']}, {city['state']}  [{sources}]")
        sys.exit(0)

    if not args.source:
        parser.error("--source is required (unless using --list-cities)")

    pipeline_run_id = args.pipeline_run_id or os.getenv("GITHUB_RUN_ID")

    result = run_sync(
        source=args.source,
        city_fips=args.city_fips,
        sync_type=args.sync_type,
        triggered_by=args.triggered_by,
        pipeline_run_id=pipeline_run_id,
    )

    print(f"\n::group::Sync Summary")
    print(json.dumps(result, indent=2, default=str))
    print(f"::endgroup::")

    if result.get("status") == "failed":
        sys.exit(1)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    main()
