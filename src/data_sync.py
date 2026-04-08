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

from pipeline_journal import PipelineJournal, check_anomalies

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
    """Sync contributions and independent expenditures from CAL-ACCESS bulk data.

    Downloads the full bulk ZIP (~1.5GB) and processes Richmond-related
    contributions (RCPT_CD) and independent expenditures (EXPN_CD).
    IE data connects PACs (e.g., Chevron's committees) to specific candidates.
    This is a heavy operation — run monthly.
    """
    from calaccess_client import (
        download_bulk_data,
        find_richmond_filers,
        find_richmond_filing_ids,
        get_richmond_contributions,
        get_richmond_expenditures,
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

    print("  Loading contributions into database...")
    stats = load_contributions_to_db(conn, contributions, city_fips=city_fips)

    print("  Extracting independent expenditures...")
    expenditures = get_richmond_expenditures(zip_path, filing_map=filing_map)
    print(f"  Found {len(expenditures):,} independent expenditures")

    print("  Loading expenditures into database...")
    exp_stats = load_expenditures_to_db(conn, expenditures, city_fips=city_fips)

    return {
        "records_fetched": len(contributions) + len(expenditures),
        "records_new": stats["contributions"] + exp_stats["loaded"],
        "records_updated": 0,
        "donors_created": stats["donors"],
        "committees_created": stats["committees"],
        "skipped": stats["skipped"] + exp_stats["skipped"],
        "expenditures_fetched": len(expenditures),
        "expenditures_loaded": exp_stats["loaded"],
    }


ESCRIBEMEETINGS_TIMEOUT = 300  # 5 minutes max per meeting scrape


def sync_escribemeetings(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Check eSCRIBE for upcoming meetings and scrape new agenda packets.

    For incremental: only checks upcoming meetings in the next 14 days.
    For full: scans the full date range (2020-present), newest first.
    """
    from escribemeetings_scraper import (
        create_session,
        discover_meetings,
        get_meeting_date,
        scrape_meeting,
    )
    from db import ingest_document, load_meeting_to_db, resolve_body_id
    from run_pipeline import convert_escribemeetings_to_scanner_format

    city_cfg = get_city_config(city_fips)

    # Build reverse mapping: eSCRIBE MeetingName → canonical body name
    comm_cfg = city_cfg["data_sources"].get("commissions_escribemeetings", {})
    escribemeetings_to_body = {v: k for k, v in comm_cfg.items()}
    escribemeetings_to_body["City Council"] = "City Council"

    session = create_session()

    if sync_type == "full":
        print("  Discovering all meetings from eSCRIBE...")
        meetings = discover_meetings(session)
        # Process newest first: recent meetings are highest value
        meetings.sort(key=lambda m: m.get("StartDate", ""), reverse=True)
    else:
        print("  Checking eSCRIBE for upcoming meetings...")
        meetings = discover_meetings(session)
        # Filter to upcoming 14 days
        from datetime import timedelta
        today = datetime.now().date()
        cutoff = today + timedelta(days=14)
        meetings = [
            m for m in meetings
            if get_meeting_date(m) != "unknown"
            and today <= datetime.strptime(get_meeting_date(m), "%Y-%m-%d").date() <= cutoff
        ]

    print(f"  Found {len(meetings)} meetings to process")

    new_count = 0
    skipped_count = 0
    error_count = 0
    errors: list[str] = []

    for i, meeting in enumerate(meetings, 1):
        meeting_date = get_meeting_date(meeting)
        meeting_name = meeting.get("MeetingName", "Unknown")

        # Check if we already have this meeting's raw data.
        # source_identifier includes meeting_name to avoid collisions when
        # council and commission meetings happen on the same date.
        source_id = f"escribemeetings_{meeting_name}_{meeting_date}"
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id FROM documents
                   WHERE city_fips = %s AND source_type = 'escribemeetings'
                     AND source_identifier IN (%s, %s)""",
                (city_fips, source_id, f"escribemeetings_{meeting_date}"),
            )
            if cur.fetchone():
                skipped_count += 1
                continue  # Already have this meeting

        print(f"  [{i}/{len(meetings)}] Scraping {meeting_date} ({meeting_name})...")
        try:
            data = _scrape_meeting_with_timeout(
                session, meeting, timeout=ESCRIBEMEETINGS_TIMEOUT,
            )
            raw_bytes = json.dumps(data, indent=2).encode("utf-8")
            doc_id = ingest_document(
                conn,
                city_fips=city_fips,
                source_type="escribemeetings",
                raw_content=raw_bytes,
                credibility_tier=1,
                source_url=data.get("meeting_url"),
                source_identifier=source_id,
                mime_type="application/json",
                metadata={
                    "meeting_date": meeting_date,
                    "meeting_name": data.get("meeting_name"),
                    "item_count": len(data.get("items", [])),
                    "pipeline": "data_sync",
                },
            )

            # Resolve body_id from meeting name → canonical body name
            body_name = escribemeetings_to_body.get(meeting_name, meeting_name)
            body_id = resolve_body_id(conn, city_fips, body_name)

            # Hydrate Layer 2: meetings + agenda_items
            scanner_data = convert_escribemeetings_to_scanner_format(data)
            load_meeting_to_db(
                conn, scanner_data,
                document_id=doc_id, city_fips=city_fips,
                body_id=body_id,
                agenda_url=data.get("portal_url"),
            )
            new_count += 1
        except Exception as e:
            error_count += 1
            error_msg = f"{meeting_date}: {e}"
            errors.append(error_msg)
            print(f"    ERROR: {e}")

        # Update sync log progress after each meeting (if we have a log ID)
        if sync_log_id and (new_count + error_count) % 5 == 0:
            _update_sync_progress(conn, sync_log_id, {
                "processed": i,
                "total": len(meetings),
                "new": new_count,
                "skipped": skipped_count,
                "errors": error_count,
                "last_date": meeting_date,
            })

    return {
        "records_fetched": len(meetings),
        "records_new": new_count,
        "records_updated": 0,
        "skipped": skipped_count,
        "errors": error_count,
        "error_details": errors[:10],  # Cap at 10 to keep metadata manageable
    }


def sync_escribemeetings_minutes(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Discover and link Post-Meeting Minutes from eSCRIBE.

    eSCRIBE stores adopted minutes as standalone documents NOT linked from
    meeting pages. Discovery requires scanning document IDs and checking
    Content-Disposition headers for the "Post-Meeting Minutes" filename pattern.
    """
    from escribemeetings_scraper import (
        create_session,
        discover_post_meeting_minutes,
    )

    session = create_session(city_fips=city_fips)

    # Determine scan start for incremental mode
    start_doc_id = 55000  # Known earliest Post-Meeting Minutes
    if sync_type == "incremental":
        with conn.cursor() as cur:
            cur.execute(
                """SELECT MAX((att->>'document_id')::int)
                   FROM documents,
                        jsonb_array_elements(
                            CASE WHEN jsonb_typeof(metadata->'items') = 'array'
                                 THEN metadata->'items'
                                 ELSE '[]'::jsonb END
                        ) AS item,
                        jsonb_array_elements(
                            CASE WHEN jsonb_typeof(item->'attachments') = 'array'
                                 THEN item->'attachments'
                                 ELSE '[]'::jsonb END
                        ) AS att
                   WHERE city_fips = %s
                     AND source_type = 'escribemeetings'""",
                (city_fips,),
            )
            row = cur.fetchone()
            if row and row[0]:
                start_doc_id = max(55000, row[0] - 500)

    print(f"  Scanning for Post-Meeting Minutes (start_doc_id={start_doc_id})...")
    minutes_docs = discover_post_meeting_minutes(
        session, start_doc_id=start_doc_id, city_fips=city_fips,
    )
    print(f"  Found {len(minutes_docs)} Post-Meeting Minutes documents")

    # Match to existing meetings and update minutes_url
    linked = 0
    already_set = 0
    no_match = 0
    for doc in minutes_docs:
        meeting_date = doc["meeting_date"]
        minutes_url = doc["url"]

        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, minutes_url FROM meetings
                   WHERE city_fips = %s AND meeting_date = %s
                     AND body_id IN (
                         SELECT id FROM bodies
                         WHERE city_fips = %s AND name = 'City Council'
                     )
                   LIMIT 1""",
                (city_fips, meeting_date, city_fips),
            )
            row = cur.fetchone()
            if not row:
                no_match += 1
                print(f"    No meeting found for {meeting_date} ({doc['filename']})")
                continue

            meeting_id, existing_url = row

            # eSCRIBE Post-Meeting Minutes are the officially adopted version.
            # Overwrite Archive Center URLs (draft/earlier source) but skip
            # if already pointing to an eSCRIBE URL.
            if existing_url and "escribemeetings" in existing_url:
                already_set += 1
                continue

            cur.execute(
                "UPDATE meetings SET minutes_url = %s WHERE id = %s",
                (minutes_url, meeting_id),
            )
            if existing_url:
                linked += 1
                print(f"    Upgraded minutes for {meeting_date}: Archive Center -> DocumentId={doc['document_id']}")
            else:
                linked += 1
                print(f"    Linked minutes for {meeting_date}: DocumentId={doc['document_id']}")

    conn.commit()
    print(f"  Results: {linked} newly linked, {already_set} already set, {no_match} no match")

    return {
        "records_fetched": len(minutes_docs),
        "records_new": linked,
        "records_updated": 0,
        "already_set": already_set,
        "no_match": no_match,
    }


def _scrape_meeting_with_timeout(
    session, meeting: dict, timeout: int = 300,
) -> dict:
    """Wrapper around scrape_meeting with a per-meeting timeout.

    Uses threading to enforce the timeout since signal-based timeouts
    don't work reliably in all environments (e.g., non-main threads).
    """
    from escribemeetings_scraper import scrape_meeting
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(scrape_meeting, session, meeting)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(
                f"Meeting scrape exceeded {timeout}s timeout"
            )


def _update_sync_progress(
    conn, sync_log_id, progress: dict,
) -> None:
    """Update sync log metadata with progress info (non-fatal on error)."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE data_sync_log
                   SET metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
                   WHERE id = %s""",
                (json.dumps({"progress": progress}), sync_log_id),
            )
        conn.commit()
    except Exception:
        pass  # Progress updates are best-effort, never block the sync


def backfill_escribemeetings_layer2(
    conn,
    city_fips: str = DEFAULT_FIPS,
) -> dict:
    """Hydrate Layer 2 (meetings + agenda_items) from existing Layer 1 eSCRIBE docs.

    Reads raw JSON from the documents table and runs the conversion +
    load pipeline for each. Idempotent: ON CONFLICT DO UPDATE in
    load_meeting_to_db means this is safe to re-run.
    """
    from run_pipeline import convert_escribemeetings_to_scanner_format
    from db import load_meeting_to_db, resolve_body_id

    city_cfg = get_city_config(city_fips)
    comm_cfg = city_cfg["data_sources"].get("commissions_escribemeetings", {})
    escribemeetings_to_body = {v: k for k, v in comm_cfg.items()}
    escribemeetings_to_body["City Council"] = "City Council"

    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, source_identifier, raw_content
               FROM documents
               WHERE city_fips = %s AND source_type = 'escribemeetings'
               ORDER BY source_identifier DESC""",
            (city_fips,),
        )
        docs = cur.fetchall()

    print(f"  Found {len(docs)} eSCRIBE documents to hydrate")

    hydrated = 0
    errors = 0

    for doc_id, source_id, raw_content in docs:
        try:
            if isinstance(raw_content, memoryview):
                raw_content = bytes(raw_content)
            escribemeetings_data = json.loads(raw_content)

            # Resolve body_id from meeting name
            meeting_name = escribemeetings_data.get("meeting_name", "")
            body_name = escribemeetings_to_body.get(meeting_name, meeting_name)
            body_id = resolve_body_id(conn, city_fips, body_name)

            scanner_data = convert_escribemeetings_to_scanner_format(escribemeetings_data)
            load_meeting_to_db(
                conn, scanner_data,
                document_id=doc_id, city_fips=city_fips,
                body_id=body_id,
            )
            hydrated += 1
            meeting_date = escribemeetings_data.get("meeting_date", "?")
            items = len(escribemeetings_data.get("items", []))
            print(f"    {meeting_date}: {items} items -> Layer 2")
        except Exception as e:
            errors += 1
            print(f"    ERROR {source_id}: {e}")

    print(f"  Hydrated {hydrated} meetings, {errors} errors")
    return {"hydrated": hydrated, "errors": errors, "total_docs": len(docs)}


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
    from nextrequest_scraper import scrape_all, save_to_db

    print("  Fetching from NextRequest client API...")
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

    # For full sync, skip per-request detail calls (much faster).
    # For incremental, fetch details to get closed_date from timeline.
    skip_details = sync_type == "full" and since_date is None

    results = scrape_all(
        since_date=since_date,
        download_docs=False,
        extract_text=False,
        skip_details=skip_details,
    )

    print(f"  Fetched {results['stats']['total_found']} requests"
          + (f", {results['stats']['details_scraped']} with details"
             if results['stats']['details_scraped'] > 0 else ""))

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


# Content-based detection for minutes vs comment compilations.
# The city sometimes publishes public comments first, then replaces the PDF
# with combined minutes+comments. Hardcoded ADID lists don't scale —
# detect by checking raw_text for structural markers of actual minutes.
_MINUTES_MARKERS = ("ROLL CALL", "called to order", "ADJOURNMENT")


def _is_minutes_content(raw_text: str) -> bool:
    """Check if raw_text contains actual meeting minutes (not just public comments).

    Returns True if the text contains structural markers like ROLL CALL,
    called to order, or ADJOURNMENT that indicate official minutes content.
    """
    if not raw_text:
        return False
    text_upper = raw_text.upper()
    return any(marker.upper() in text_upper for marker in _MINUTES_MARKERS)


def sync_minutes_extraction(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
    limit: int | None = None,
    amid: int | None = None,
    body_type: str = "city_council",
) -> dict:
    """Extract structured meeting data from Archive Center minutes PDFs.

    Reads documents from Layer 1, runs Claude extraction via
    extract_with_tool_use(), records the extraction run, and loads
    structured data into Layer 2 tables (meetings, agenda_items, motions,
    votes, meeting_attendance).

    Args:
        amid: Override the target AMID. Default: minutes_amid from config (31).
            Use commission_amids values for commission minutes extraction.
        body_type: Body type for extraction prompt selection and role mapping.
            'city_council' (default), 'commission', 'board', etc.

    For incremental: only extracts documents with no current extraction_runs entry.
    For full: re-extracts all documents for the target AMID.
    """
    import time
    from pipeline import extract_with_tool_use
    from db import save_extraction_run, load_meeting_to_db, resolve_body_id

    city_cfg = get_city_config(city_fips)
    ac_cfg = city_cfg["data_sources"].get("archive_center", {})
    minutes_amid = amid or ac_cfg.get("minutes_amid", 31)

    # Resolve body_id from AMID → commission name → body
    body_id = None
    if amid is not None and amid != ac_cfg.get("minutes_amid", 31):
        commission_amids = ac_cfg.get("commission_amids", {})
        # Reverse lookup: AMID → body name
        amid_to_body = {v: k for k, v in commission_amids.items()}
        body_name = amid_to_body.get(amid)
        if body_name:
            body_id = resolve_body_id(conn, city_fips, body_name)
    elif amid is None or amid == ac_cfg.get("minutes_amid", 31):
        body_id = resolve_body_id(conn, city_fips, "City Council")

    # Find AMID minutes documents that need extraction.
    # Only fetch id + metadata (not raw_text) to avoid loading 20+ MB in one query.
    # raw_text is lazy-loaded per document before each API call.
    with conn.cursor() as cur:
        if sync_type == "full":
            cur.execute(
                """SELECT d.id, d.metadata
                   FROM documents d
                   WHERE d.city_fips = %s
                     AND d.source_type = 'archive_center'
                     AND (d.metadata->>'amid')::int = %s
                     AND d.raw_text IS NOT NULL
                     AND d.raw_text != ''
                   ORDER BY d.metadata->>'date' DESC""",
                (city_fips, minutes_amid),
            )
        else:
            cur.execute(
                """SELECT d.id, d.metadata
                   FROM documents d
                   WHERE d.city_fips = %s
                     AND d.source_type = 'archive_center'
                     AND (d.metadata->>'amid')::int = %s
                     AND d.raw_text IS NOT NULL
                     AND d.raw_text != ''
                     AND NOT EXISTS (
                         SELECT 1 FROM extraction_runs er
                         WHERE er.document_id = d.id AND er.is_current = TRUE
                     )
                   ORDER BY d.metadata->>'date' DESC""",
                (city_fips, minutes_amid),
            )
        docs = cur.fetchall()

    # Filter out comment compilations using content-based detection.
    # Uses SQL-level check for ROLL CALL / ADJOURNMENT markers to avoid
    # loading full raw_text into Python for every candidate document.
    filtered = []
    comment_only = 0
    with conn.cursor() as cur:
        for doc_id, metadata in docs:
            cur.execute(
                """SELECT (
                    POSITION('ROLL CALL' IN raw_text) > 0
                    OR POSITION('called to order' IN LOWER(raw_text)) > 0
                    OR POSITION('ADJOURNMENT' IN raw_text) > 0
                ) FROM documents WHERE id = %s""",
                (doc_id,),
            )
            is_minutes = cur.fetchone()[0]
            if is_minutes:
                filtered.append((doc_id, metadata))
            else:
                comment_only += 1

    if comment_only:
        print(f"  Skipped {comment_only} comment-only documents (no minutes markers)")

    total_eligible = len(filtered)
    if limit is not None and limit < total_eligible:
        filtered = filtered[:limit]
        print(f"  Found {total_eligible} minutes documents to extract (processing {limit} this run)")
    else:
        print(f"  Found {total_eligible} minutes documents to extract")

    extracted = 0
    errors = 0
    error_details: list[str] = []

    for i, (doc_id, metadata) in enumerate(filtered, 1):
        doc_title = (metadata or {}).get("title", "unknown")
        doc_date = (metadata or {}).get("date", "unknown")
        print(f"  [{i}/{len(filtered)}] Extracting {doc_date}: {doc_title[:60]}...")

        try:
            # Lazy-load raw_text per document to avoid fetching all texts upfront.
            # The candidate query only fetches id+metadata (~KB each); raw_text can
            # be 100KB+ per doc, and loading all 700+ at once stalled for ~40 min.
            with conn.cursor() as cur:
                cur.execute("SELECT raw_text FROM documents WHERE id = %s", (doc_id,))
                raw_text = cur.fetchone()[0]

            data, usage = extract_with_tool_use(
                raw_text, return_usage=True, body_type=body_type,
            )

            # Estimate cost (Sonnet input $3/MTok, output $15/MTok)
            cost = (
                usage["input_tokens"] * 3.0 / 1_000_000
                + usage["output_tokens"] * 15.0 / 1_000_000
            )

            prompt_ver = "extraction_v1" if body_type == "city_council" else f"extraction_v1_{body_type}"
            save_extraction_run(
                conn,
                document_id=doc_id,
                extracted_data=data,
                model="claude-sonnet-4-20250514",
                prompt_version=prompt_ver,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                cost_usd=round(cost, 4),
            )

            load_meeting_to_db(
                conn, data,
                document_id=doc_id, city_fips=city_fips,
                body_id=body_id,
            )

            conn.commit()  # Commit each document independently

            extracted += 1
            meeting_date = data.get("meeting_date", "unknown")
            n_action = len(data.get("action_items", []))
            n_consent = len((data.get("consent_calendar") or {}).get("items", []))
            print(f"    -> {meeting_date}: {n_consent} consent + {n_action} action items"
                  f" ({usage['input_tokens']}+{usage['output_tokens']} tokens, ${cost:.4f})")

            # Brief pause between API calls
            if i < len(filtered):
                time.sleep(2)

        except Exception as e:
            conn.rollback()  # Clear failed transaction so next iteration works
            errors += 1
            error_details.append(f"{doc_date}: {e}")
            print(f"    ERROR: {e}")

        # Update sync log progress
        if sync_log_id and (extracted + errors) % 5 == 0:
            _update_sync_progress(conn, sync_log_id, {
                "processed": i,
                "total": len(filtered),
                "extracted": extracted,
                "errors": errors,
            })

    return {
        "records_fetched": len(filtered),
        "records_new": extracted,
        "records_updated": 0,
        "errors": errors,
        "error_details": error_details[:10],
    }


def refresh_stale_minutes(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
    limit: int | None = None,
) -> dict:
    """Re-download Archive Center minutes that may have been updated in-place.

    The city sometimes publishes a comment-only PDF first, then replaces it
    with the combined minutes+comments version under the same ADID. This
    function finds documents that were extracted but lack minutes markers
    (ROLL CALL, called to order, ADJOURNMENT), re-downloads the PDF, and
    if the content changed, inserts a new document row for extraction.

    Returns stats dict with counts of refreshed/unchanged/errors.
    """
    import hashlib
    from archive_center_discovery import (
        create_session, extract_text, CIVICPLUS_BASE_URL, ARCHIVE_DOCUMENT_URL,
    )

    city_cfg = get_city_config(city_fips)
    ac_cfg = city_cfg["data_sources"].get("archive_center", {})
    minutes_amid = ac_cfg.get("minutes_amid", 31)

    # Find documents that have extraction runs but no minutes content
    with conn.cursor() as cur:
        cur.execute(
            """SELECT d.id, d.metadata, d.content_hash
               FROM documents d
               JOIN extraction_runs er ON er.document_id = d.id AND er.is_current = TRUE
               WHERE d.city_fips = %s
                 AND d.source_type = 'archive_center'
                 AND (d.metadata->>'amid')::int = %s
                 AND d.raw_text IS NOT NULL
                 AND NOT (
                     POSITION('ROLL CALL' IN d.raw_text) > 0
                     OR POSITION('called to order' IN LOWER(d.raw_text)) > 0
                     OR POSITION('ADJOURNMENT' IN d.raw_text) > 0
                 )
               ORDER BY d.ingested_at DESC""",
            (city_fips, minutes_amid),
        )
        stale_docs = cur.fetchall()

    if limit:
        stale_docs = stale_docs[:limit]

    if not stale_docs:
        print("  No stale minutes documents found.")
        return {"checked": 0, "refreshed": 0, "unchanged": 0, "errors": 0}

    print(f"  Found {len(stale_docs)} extracted documents without minutes markers — checking for updates...")

    session = create_session()
    from db import ingest_document
    import fitz
    import time

    refreshed = 0
    unchanged = 0
    errors = 0

    for i, (doc_id, metadata, old_hash) in enumerate(stale_docs, 1):
        adid = str((metadata or {}).get("adid", ""))
        title = (metadata or {}).get("title", "unknown")
        print(f"  [{i}/{len(stale_docs)}] Checking ADID {adid}: {title[:60]}...")

        try:
            url = f"{CIVICPLUS_BASE_URL}{ARCHIVE_DOCUMENT_URL.format(adid=adid)}"
            resp = session.get(url, timeout=60)
            resp.raise_for_status()
            pdf_bytes = resp.content

            new_hash = hashlib.sha256(pdf_bytes).hexdigest()
            if new_hash == old_hash:
                print(f"    Content unchanged (hash match)")
                unchanged += 1
                continue

            # Extract text from updated PDF
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            raw_text = ""
            for page in doc:
                raw_text += page.get_text()
            doc.close()

            if not _is_minutes_content(raw_text):
                print(f"    New content still lacks minutes markers — skipping")
                unchanged += 1
                continue

            # Insert new document with updated content
            new_doc_id = ingest_document(
                conn,
                city_fips=city_fips,
                source_type="archive_center",
                raw_content=pdf_bytes,
                raw_text=raw_text.replace("\x00", ""),
                credibility_tier=1,
                source_url=url,
                source_identifier=f"archive_center_ADID_{adid}",
                mime_type="application/pdf",
                metadata={
                    "amid": int((metadata or {}).get("amid", 31)),
                    "amid_name": (metadata or {}).get("amid_name"),
                    "adid": adid,
                    "title": (metadata or {}).get("title"),
                    "date": (metadata or {}).get("date"),
                    "pipeline": "archive_center_discovery",
                    "refreshed_from": str(doc_id),
                },
            )
            print(f"    Updated! New document {new_doc_id} ({len(raw_text):,} chars, "
                  f"has ROLL CALL: {'ROLL CALL' in raw_text})")
            refreshed += 1

        except Exception as e:
            if "duplicate" in str(e).lower():
                print(f"    Already refreshed (duplicate hash)")
                unchanged += 1
            else:
                print(f"    ERROR: {e}")
                errors += 1

        if i < len(stale_docs):
            time.sleep(1)

    conn.commit()
    print(f"  Refresh complete: {refreshed} updated, {unchanged} unchanged, {errors} errors")
    return {
        "checked": len(stale_docs),
        "refreshed": refreshed,
        "unchanged": unchanged,
        "errors": errors,
    }


def submit_minutes_batch(
    conn,
    city_fips: str,
    limit: int | None = None,
) -> dict:
    """Submit unextracted minutes documents as an Anthropic Batch API job.

    Builds batch requests for all eligible AMID=31 documents that lack
    extraction_runs entries, submits them via the Batch API (50% cost
    reduction), and returns the batch ID for later collection.

    Returns:
        Dict with batch_id, documents_submitted, and estimated_cost.
    """
    from pipeline import build_batch_request, submit_extraction_batch

    city_cfg = get_city_config(city_fips)
    ac_cfg = city_cfg["data_sources"].get("archive_center", {})
    minutes_amid = ac_cfg.get("minutes_amid", 31)

    # Find unextracted candidates (same query as sync_minutes_extraction)
    with conn.cursor() as cur:
        cur.execute(
            """SELECT d.id, d.metadata
               FROM documents d
               WHERE d.city_fips = %s
                 AND d.source_type = 'archive_center'
                 AND (d.metadata->>'amid')::int = %s
                 AND d.raw_text IS NOT NULL
                 AND d.raw_text != ''
                 AND NOT EXISTS (
                     SELECT 1 FROM extraction_runs er
                     WHERE er.document_id = d.id AND er.is_current = TRUE
                 )
               ORDER BY d.metadata->>'date' DESC""",
            (city_fips, minutes_amid),
        )
        docs = cur.fetchall()

    # Filter out comment compilations using content-based detection
    filtered = []
    with conn.cursor() as cur:
        for doc_id, metadata in docs:
            cur.execute(
                """SELECT (
                    POSITION('ROLL CALL' IN raw_text) > 0
                    OR POSITION('called to order' IN LOWER(raw_text)) > 0
                    OR POSITION('ADJOURNMENT' IN raw_text) > 0
                ) FROM documents WHERE id = %s""",
                (doc_id,),
            )
            if cur.fetchone()[0]:
                filtered.append((doc_id, metadata))

    if limit is not None and limit < len(filtered):
        filtered = filtered[:limit]

    if not filtered:
        print("  No documents to submit.")
        return {"batch_id": None, "documents_submitted": 0}

    print(f"  Building batch requests for {len(filtered)} documents...")

    # Build batch requests, lazy-loading raw_text per document
    requests = []
    for i, (doc_id, metadata) in enumerate(filtered, 1):
        title = (metadata or {}).get("title", "unknown")[:50]
        date = (metadata or {}).get("date", "?")
        if i % 50 == 0 or i == len(filtered):
            print(f"    [{i}/{len(filtered)}] {date}: {title}")

        with conn.cursor() as cur:
            cur.execute("SELECT raw_text FROM documents WHERE id = %s", (doc_id,))
            raw_text = cur.fetchone()[0]

        requests.append(build_batch_request(str(doc_id), raw_text))

    print(f"  Submitting batch of {len(requests)} requests...")
    batch_id = submit_extraction_batch(requests)

    # Rough cost estimate (batch = 50% of standard)
    avg_cost_per_doc = 0.119  # from observed 39-doc run
    est_cost = len(requests) * avg_cost_per_doc * 0.5
    print(f"  Batch submitted: {batch_id}")
    print(f"  Estimated cost: ~${est_cost:.0f} (50% batch discount)")
    print(f"  Results typically ready in 1-24 hours.")
    print(f"")
    print(f"  To check status:")
    print(f"    python data_sync.py --batch-status {batch_id}")
    print(f"  To collect results when done:")
    print(f"    python data_sync.py --collect-batch {batch_id}")

    return {
        "batch_id": batch_id,
        "documents_submitted": len(requests),
        "estimated_cost_usd": round(est_cost, 2),
    }


def collect_minutes_batch(
    conn,
    batch_id: str,
    city_fips: str,
) -> dict:
    """Collect results from a completed Anthropic batch job.

    Iterates over batch results, saves extraction_runs, and loads
    structured data into Layer 2 tables.

    Returns:
        Dict with records_new, errors, and cost details.
    """
    from pipeline import (
        check_batch_status, collect_batch_results as iter_batch_results,
    )
    from db import save_extraction_run, load_meeting_to_db

    # Check status first
    status = check_batch_status(batch_id)
    print(f"  Batch status: {status['processing_status']}")
    print(f"  Counts: {status['request_counts']}")

    if status["processing_status"] != "ended":
        print(f"  Batch is still {status['processing_status']}. Try again later.")
        return {
            "status": status["processing_status"],
            "request_counts": status["request_counts"],
        }

    extracted = 0
    errors = 0
    error_details = []
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0

    total = (
        status["request_counts"]["succeeded"]
        + status["request_counts"]["errored"]
        + status["request_counts"]["canceled"]
        + status["request_counts"]["expired"]
    )

    print(f"  Processing {total} results...")

    for custom_id, data, info in iter_batch_results(batch_id):
        doc_id = custom_id  # UUID string

        if data is None:
            errors += 1
            error_details.append(f"{doc_id}: {info}")
            print(f"    ERROR {doc_id}: {info}")
            continue

        usage = info  # For succeeded results, info is the usage dict
        # Batch API = 50% discount: Sonnet input $1.50/MTok, output $7.50/MTok
        cost = (
            usage["input_tokens"] * 1.5 / 1_000_000
            + usage["output_tokens"] * 7.5 / 1_000_000
        )
        total_input_tokens += usage["input_tokens"]
        total_output_tokens += usage["output_tokens"]
        total_cost += cost

        # Save extraction run (always, even if loading fails — we have the data)
        save_extraction_run(
            conn,
            document_id=doc_id,
            extracted_data=data,
            model="claude-sonnet-4-20250514",
            prompt_version="extraction_v1_batch",
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cost_usd=round(cost, 4),
        )

        try:
            load_meeting_to_db(
                conn, data,
                document_id=doc_id, city_fips=city_fips,
            )
        except Exception as e:
            conn.rollback()  # Clear failed transaction so next iteration works
            errors += 1
            meeting_date = data.get("meeting_date", "?")
            error_details.append(f"{doc_id} ({meeting_date}): {e}")
            print(f"    LOAD ERROR {doc_id} ({meeting_date}): {e}")
            continue

        extracted += 1
        meeting_date = data.get("meeting_date", "?")
        n_action = len(data.get("action_items", []))
        n_consent = len((data.get("consent_calendar") or {}).get("items", []))

        if extracted % 25 == 0 or extracted == 1:
            print(f"    [{extracted}] {meeting_date}: {n_consent} consent + {n_action} action (${cost:.4f})")

    print(f"\n  Batch collection complete:")
    print(f"    Extracted: {extracted}")
    print(f"    Errors:    {errors}")
    print(f"    Tokens:    {total_input_tokens:,} in / {total_output_tokens:,} out")
    print(f"    Cost:      ${total_cost:.2f} (at batch rates)")

    return {
        "records_new": extracted,
        "errors": errors,
        "error_details": error_details[:10],
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_cost_usd": round(total_cost, 2),
    }


def sync_socrata_payroll(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync city employee payroll from Socrata open data portal.

    Wraps the existing payroll_ingester pipeline: fetch from Socrata,
    aggregate per-transaction rows by employee, classify hierarchy,
    and upsert into city_employees table.

    For incremental: fetches latest fiscal year only.
    For full: fetches all available fiscal years.
    """
    from payroll_ingester import fetch_payroll, parse_payroll_records, load_to_db

    # Determine which fiscal years to process
    if sync_type == "full":
        # Socrata data goes back several years; fetch recent ones
        from datetime import date
        current_fy = str(date.today().year)
        fiscal_years = [str(int(current_fy) - i) for i in range(5)]
    else:
        from datetime import date
        fiscal_years = [str(date.today().year)]

    total_fetched = 0
    total_loaded = 0

    for fy in fiscal_years:
        print(f"  Fetching payroll for FY {fy}...")
        raw_rows = fetch_payroll(fy, city_fips=city_fips)
        if not raw_rows:
            print(f"    No payroll data for FY {fy}")
            continue

        records = parse_payroll_records(raw_rows, city_fips=city_fips)
        total_fetched += len(raw_rows)
        total_loaded += len(records)

        print(f"    {len(raw_rows)} raw rows -> {len(records)} employees")

        # load_to_db manages its own connection; pass records through conn instead
        with conn.cursor() as cur:
            loaded = 0
            for rec in records:
                cur.execute(
                    """INSERT INTO city_employees
                       (city_fips, name, normalized_name, job_title, department,
                        is_department_head, hierarchy_level, annual_salary,
                        total_compensation, fiscal_year, is_current, source,
                        socrata_record_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT ON CONSTRAINT uq_city_employee
                       DO UPDATE SET
                           job_title = EXCLUDED.job_title,
                           is_department_head = EXCLUDED.is_department_head,
                           hierarchy_level = EXCLUDED.hierarchy_level,
                           annual_salary = EXCLUDED.annual_salary,
                           total_compensation = EXCLUDED.total_compensation,
                           is_current = EXCLUDED.is_current,
                           source = EXCLUDED.source,
                           socrata_record_id = EXCLUDED.socrata_record_id,
                           updated_at = NOW()""",
                    (
                        rec["city_fips"], rec["name"], rec["normalized_name"],
                        rec["job_title"], rec["department"],
                        rec["is_department_head"], rec["hierarchy_level"],
                        rec["annual_salary"], rec["total_compensation"],
                        rec["fiscal_year"], rec["is_current"], rec["source"],
                        rec.get("socrata_record_id"),
                    ),
                )
                loaded += 1
            conn.commit()
            print(f"    Loaded {loaded} records")

    print(f"  Payroll sync complete: {total_fetched} raw rows -> {total_loaded} employees")

    return {
        "records_fetched": total_fetched,
        "records_new": total_loaded,
        "records_updated": 0,
        "fiscal_years_processed": len(fiscal_years),
    }


def _normalize_vendor_name(name: str) -> str:
    """Normalize vendor name for matching: lowercase, collapse whitespace."""
    if not name:
        return ""
    return " ".join(name.lower().split())


def sync_socrata_expenditures(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync city expenditure records from Socrata open data portal.

    Fetches actual spending data (vendor, amount, department, fund) and
    upserts into city_expenditures table.

    For incremental: fetches latest fiscal year only.
    For full: fetches all available fiscal years.
    """
    from socrata_client import query_dataset

    # Determine fiscal years to process
    if sync_type == "full":
        from datetime import date
        current_fy = str(date.today().year)
        fiscal_years = [str(int(current_fy) - i) for i in range(5)]
    else:
        from datetime import date
        fiscal_years = [str(date.today().year)]

    total_fetched = 0
    total_new = 0
    total_updated = 0

    for fy in fiscal_years:
        print(f"  Fetching expenditures for FY {fy}...")

        # Paginate through all results (Socrata max 50K per call)
        offset = 0
        batch_size = 50000
        fy_rows = []

        while True:
            rows = query_dataset(
                "expenditures",
                where=f"fiscalyear = '{fy}'",
                limit=batch_size,
                offset=offset,
                city_fips=city_fips,
            )
            if not rows:
                break
            fy_rows.extend(rows)
            if len(rows) < batch_size:
                break
            offset += batch_size

        if not fy_rows:
            print(f"    No expenditure data for FY {fy}")
            continue

        total_fetched += len(fy_rows)
        print(f"    {len(fy_rows)} expenditure records")

        # Upsert into city_expenditures
        new = 0
        updated = 0
        with conn.cursor() as cur:
            for row in fy_rows:
                vendor = (row.get("vendorname") or "").strip()
                amount_raw = row.get("actual")
                amount = None
                if amount_raw is not None:
                    try:
                        amount = float(amount_raw)
                    except (ValueError, TypeError):
                        amount = None

                # Parse date (Socrata returns ISO format or floating timestamp)
                exp_date = None
                date_raw = row.get("date")
                if date_raw:
                    # Socrata dates come as ISO strings like "2025-01-15T00:00:00.000"
                    try:
                        exp_date = date_raw[:10]  # YYYY-MM-DD portion
                    except (IndexError, TypeError):
                        exp_date = None

                # Socrata rows have a ":id" field as unique row identifier
                socrata_id = row.get(":id") or row.get("rowid") or ""
                if not socrata_id:
                    # Construct a synthetic ID from key fields
                    socrata_id = f"{fy}:{vendor}:{amount}:{date_raw}"

                cur.execute(
                    """INSERT INTO city_expenditures
                       (city_fips, vendor_name, normalized_vendor, description,
                        amount, department, fund, fiscal_year, expenditure_date,
                        source, socrata_row_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT ON CONSTRAINT uq_city_expenditure
                       DO UPDATE SET
                           vendor_name = EXCLUDED.vendor_name,
                           description = EXCLUDED.description,
                           amount = EXCLUDED.amount,
                           department = EXCLUDED.department,
                           fund = EXCLUDED.fund,
                           expenditure_date = EXCLUDED.expenditure_date,
                           updated_at = NOW()
                       RETURNING (xmax = 0) AS inserted""",
                    (
                        city_fips,
                        vendor,
                        _normalize_vendor_name(vendor),
                        (row.get("description") or "").strip()[:1000],
                        amount,
                        (row.get("organization") or "").strip(),
                        (row.get("fund") or "").strip(),
                        fy,
                        exp_date,
                        "socrata_expenditures",
                        socrata_id,
                    ),
                )
                result_row = cur.fetchone()
                if result_row and result_row[0]:
                    new += 1
                else:
                    updated += 1

            conn.commit()

        total_new += new
        total_updated += updated
        print(f"    Loaded: {new} new, {updated} updated")

    print(f"  Expenditures sync complete: {total_fetched} records ({total_new} new, {total_updated} updated)")

    return {
        "records_fetched": total_fetched,
        "records_new": total_new,
        "records_updated": total_updated,
        "fiscal_years_processed": len(fiscal_years),
    }


def _parse_socrata_date(raw: str | None) -> str | None:
    """Parse Socrata date fields into YYYY-MM-DD.

    Handles two formats:
    - ISO: '2019-07-17T00:00:00.000'
    - Text: 'Jan 14 2013 12:00AM'
    Returns None for unparseable values.
    """
    if not raw:
        return None
    raw = raw.strip()
    # ISO format
    if len(raw) >= 10 and raw[4:5] == "-":
        return raw[:10]
    # Text format: 'Mon DD YYYY ...'
    from datetime import datetime
    for fmt in ("%b %d %Y %I:%M%p", "%b  %d %Y %I:%M%p", "%b %d %Y"):
        try:
            return datetime.strptime(raw.split(" 12:")[0] if " 12:" in raw else raw[:11].strip(), fmt.replace(" 12:", "")).strftime("%Y-%m-%d")
        except (ValueError, IndexError):
            continue
    # Last resort: try dateutil-style parsing
    try:
        return raw[:10] if len(raw) >= 10 else None
    except Exception:
        return None


def _sync_socrata_paginated(
    dataset_key: str,
    city_fips: str,
    process_row,
    table_name: str,
    conn,
    insert_sql: str,
    source_label: str,
    where: str | None = None,
) -> dict:
    """Shared pagination + upsert loop for Socrata regulatory datasets.

    Args:
        dataset_key: Socrata dataset key (e.g., 'permit_trak')
        city_fips: FIPS code
        process_row: callable(row) -> tuple of values for INSERT, or None to skip
        table_name: for logging
        conn: database connection
        insert_sql: full INSERT ... ON CONFLICT SQL with %s placeholders
        source_label: for logging
        where: optional SoQL WHERE clause
    """
    from socrata_client import query_dataset

    total_fetched = 0
    total_new = 0
    total_updated = 0
    offset = 0
    batch_size = 50000

    while True:
        rows = query_dataset(
            dataset_key,
            where=where,
            limit=batch_size,
            offset=offset,
            city_fips=city_fips,
        )
        if not rows:
            break

        total_fetched += len(rows)
        batch_new = 0
        batch_updated = 0

        with conn.cursor() as cur:
            for row in rows:
                values = process_row(row)
                if values is None:
                    continue
                cur.execute(insert_sql, values)
                result_row = cur.fetchone()
                if result_row and result_row[0]:
                    batch_new += 1
                else:
                    batch_updated += 1

        conn.commit()
        total_new += batch_new
        total_updated += batch_updated
        print(f"    {table_name}: batch {offset // batch_size + 1} — {len(rows)} rows ({batch_new} new, {batch_updated} updated)")

        if len(rows) < batch_size:
            break
        offset += batch_size

    print(f"  {source_label} sync complete: {total_fetched} records ({total_new} new, {total_updated} updated)")
    return {
        "records_fetched": total_fetched,
        "records_new": total_new,
        "records_updated": total_updated,
    }


def sync_socrata_permits(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync building/development permit records from Socrata permit_trak.

    For incremental: fetches permits applied in the last 90 days.
    For full: fetches all permits (~177K records).
    """
    where = None
    if sync_type != "full":
        where = "applied > '2025-01-01T00:00:00'"  # Recent permits

    def process_row(row: dict) -> tuple:
        socrata_id = row.get(":id") or row.get("permit_no") or ""
        return (
            city_fips,
            (row.get("permit_no") or "").strip()[:50],
            (row.get("type") or "").strip()[:100],
            (row.get("subtype") or "").strip()[:100],
            (row.get("description") or "").strip()[:2000] or None,
            (row.get("status") or "").strip()[:50],
            (row.get("situs_address") or "").strip()[:500] or None,
            (row.get("situs_apn") or "").strip()[:50] or None,
            _parse_socrata_date(row.get("applied")),
            _parse_socrata_date(row.get("approved")),
            _parse_socrata_date(row.get("issued")),
            _parse_socrata_date(row.get("finaled")),
            _parse_socrata_date(row.get("expired")),
            (row.get("applied_by") or "").strip()[:200] or None,
            _safe_numeric(row.get("fees_charged")),
            _safe_numeric(row.get("fees_paid")),
            _safe_numeric(row.get("jobvalue")),
            _safe_numeric(row.get("bldg_sf")),
            _safe_int(row.get("no_units")),
            (row.get("project_number") or "").strip()[:100] or None,
            "socrata_permits",
            socrata_id,
        )

    return _sync_socrata_paginated(
        dataset_key="permit_trak",
        city_fips=city_fips,
        process_row=process_row,
        table_name="city_permits",
        conn=conn,
        where=where,
        insert_sql="""INSERT INTO city_permits
            (city_fips, permit_no, permit_type, permit_subtype, description,
             status, situs_address, situs_apn,
             applied_date, approved_date, issued_date, finaled_date, expired_date,
             applied_by, fees_charged, fees_paid, job_value, building_sqft, units,
             project_number, source, socrata_row_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT ON CONSTRAINT uq_city_permit
            DO UPDATE SET
                status = EXCLUDED.status,
                approved_date = EXCLUDED.approved_date,
                issued_date = EXCLUDED.issued_date,
                finaled_date = EXCLUDED.finaled_date,
                expired_date = EXCLUDED.expired_date,
                fees_paid = EXCLUDED.fees_paid,
                updated_at = NOW()
            RETURNING (xmax = 0) AS inserted""",
        source_label="Permits",
    )


def sync_socrata_licenses(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync business license records from Socrata license_trak.

    For incremental: fetches licenses issued in the last year.
    For full: fetches all licenses (~6K records).
    """
    where = None
    if sync_type != "full":
        where = "bus_lic_iss > '2025-01-01T00:00:00'"

    def process_row(row: dict) -> tuple:
        socrata_id = row.get(":id") or ""
        company = (row.get("company") or "").strip()
        return (
            city_fips,
            company[:500],
            _normalize_vendor_name(company)[:500],
            (row.get("company_print_as") or "").strip()[:500] or None,
            (row.get("business_type") or "").strip()[:200] or None,
            (row.get("classification") or "").strip()[:200] or None,
            (row.get("ownership_type") or "").strip()[:100] or None,
            (row.get("status") or "").strip()[:50] or None,
            _safe_int(row.get("employees")),
            _parse_socrata_date(row.get("bus_lic_iss")),
            _parse_socrata_date(row.get("bus_lic_exp")),
            _parse_socrata_date(row.get("bus_start_date")),
            (row.get("loc_address1") or "").strip()[:500] or None,
            (row.get("loc_city") or "").strip()[:100] or None,
            (row.get("loc_zip") or "").strip()[:20] or None,
            " ".join(filter(None, [
                (row.get("site_number") or "").strip(),
                (row.get("site_streetname") or "").strip(),
                (row.get("site_unit_no") or "").strip(),
            ]))[:500] or None,
            (row.get("site_apn10") or row.get("site_apn") or "").strip()[:50] or None,
            (row.get("sic_1") or "").strip()[:50] or None,
            (row.get("nbrhd_council") or "").strip()[:100] or None,
            "socrata_licenses",
            socrata_id,
        )

    return _sync_socrata_paginated(
        dataset_key="license_trak",
        city_fips=city_fips,
        process_row=process_row,
        table_name="city_licenses",
        conn=conn,
        where=where,
        insert_sql="""INSERT INTO city_licenses
            (city_fips, company, normalized_company, company_dba,
             business_type, classification, ownership_type, status, employees,
             license_issued, license_expired, business_start_date,
             loc_address, loc_city, loc_zip,
             site_address, site_apn, sic_code, neighborhood_council,
             source, socrata_row_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT ON CONSTRAINT uq_city_license
            DO UPDATE SET
                status = EXCLUDED.status,
                license_expired = EXCLUDED.license_expired,
                employees = EXCLUDED.employees,
                updated_at = NOW()
            RETURNING (xmax = 0) AS inserted""",
        source_label="Licenses",
    )


def sync_socrata_code_cases(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync code enforcement cases from Socrata code_trak.

    For incremental: fetches cases opened in the last 90 days.
    For full: fetches all cases (~37K records).
    """
    where = None
    if sync_type != "full":
        where = "opened > '2025-01-01T00:00:00'"

    def process_row(row: dict) -> tuple:
        socrata_id = row.get(":id") or ""
        site_addr = (row.get("site_addr") or "").strip()
        if not site_addr:
            site_addr = " ".join(filter(None, [
                (row.get("site_number") or "").strip(),
                (row.get("site_streetname") or "").strip(),
                (row.get("site_unit_no") or "").strip(),
            ]))
        return (
            city_fips,
            (row.get("casetype") or "").strip()[:100] or None,
            (row.get("casesubtype") or "").strip()[:200] or None,
            (row.get("violation_type") or "").strip()[:200] or None,
            (row.get("violation") or "").strip()[:500] or None,
            (row.get("status") or "").strip()[:50] or None,
            (row.get("case_location") or "").strip()[:500] or None,
            site_addr[:500] or None,
            (row.get("site_apn10") or row.get("site_apn") or "").strip()[:50] or None,
            (row.get("site_zip") or "").strip()[:20] or None,
            _parse_socrata_date(row.get("opened")),
            _parse_socrata_date(row.get("closed")),
            _parse_socrata_date(row.get("date_observed")),
            _parse_socrata_date(row.get("date_corrected")),
            (row.get("nbrhd_council") or "").strip()[:100] or None,
            "socrata_code_cases",
            socrata_id,
        )

    return _sync_socrata_paginated(
        dataset_key="code_trak",
        city_fips=city_fips,
        process_row=process_row,
        table_name="city_code_cases",
        conn=conn,
        where=where,
        insert_sql="""INSERT INTO city_code_cases
            (city_fips, case_type, case_subtype, violation_type, violation,
             status, case_location, site_address, site_apn, site_zip,
             opened_date, closed_date, date_observed, date_corrected,
             neighborhood_council, source, socrata_row_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT ON CONSTRAINT uq_city_code_case
            DO UPDATE SET
                status = EXCLUDED.status,
                closed_date = EXCLUDED.closed_date,
                date_corrected = EXCLUDED.date_corrected,
                updated_at = NOW()
            RETURNING (xmax = 0) AS inserted""",
        source_label="Code cases",
    )


def sync_socrata_service_requests(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync citizen service requests from Socrata crm_trak.

    For incremental: fetches requests created in the last 90 days.
    For full: fetches all requests (~44K records).
    """
    where = None
    if sync_type != "full":
        where = "created_datetime > '2025-01-01T00:00:00'"

    def process_row(row: dict) -> tuple:
        socrata_id = row.get(":id") or ""
        lat = _safe_numeric(row.get("lat"))
        lon = _safe_numeric(row.get("lon"))
        return (
            city_fips,
            (row.get("issue_concern_type") or "").strip()[:300] or None,
            (row.get("department") or "").strip()[:200] or None,
            (row.get("description") or "").strip()[:2000] or None,
            (row.get("status") or "").strip()[:50] or None,
            (row.get("created_via") or "").strip()[:100] or None,
            (row.get("issue_address") or "").strip()[:500] or None,
            _parse_socrata_date(row.get("created_datetime")),
            _parse_socrata_date(row.get("due_date")),
            _parse_socrata_date(row.get("completed_date")),
            (row.get("linked_doc") or "").strip()[:500] or None,
            lat,
            lon,
            "socrata_service_requests",
            socrata_id,
        )

    return _sync_socrata_paginated(
        dataset_key="crm_trak",
        city_fips=city_fips,
        process_row=process_row,
        table_name="city_service_requests",
        conn=conn,
        where=where,
        insert_sql="""INSERT INTO city_service_requests
            (city_fips, issue_type, department, description, status,
             created_via, issue_address, created_date, due_date, completed_date,
             linked_doc, latitude, longitude, source, socrata_row_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT ON CONSTRAINT uq_city_service_request
            DO UPDATE SET
                status = EXCLUDED.status,
                completed_date = EXCLUDED.completed_date,
                updated_at = NOW()
            RETURNING (xmax = 0) AS inserted""",
        source_label="Service requests",
    )


def sync_socrata_projects(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync capital/development project records from Socrata project_trak.

    For incremental: fetches projects applied in the last year.
    For full: fetches all projects (~5K records).
    """
    where = None
    if sync_type != "full":
        where = "applied > '2025-01-01T00:00:00'"

    def process_row(row: dict) -> tuple:
        socrata_id = row.get(":id") or ""
        site_addr = (row.get("site_addr") or "").strip()
        if not site_addr:
            site_addr = " ".join(filter(None, [
                str(row.get("site_number") or "").strip(),
                (row.get("site_streetname") or "").strip(),
                (row.get("site_unit_no") or "").strip(),
            ]))
        return (
            city_fips,
            (row.get("project_no") or "").strip()[:50] or None,
            (row.get("project_name") or "").strip()[:500] or None,
            (row.get("projecttype") or "").strip()[:100] or None,
            (row.get("projectsubtype") or "").strip()[:200] or None,
            (row.get("description_of_work") or "").strip()[:2000] or None,
            (row.get("status") or "").strip()[:50] or None,
            site_addr[:500] or None,
            (row.get("site_apn10") or row.get("site_apn") or "").strip()[:50] or None,
            (row.get("site_zip") or "").strip()[:20] or None,
            (row.get("zoning_code1") or "").strip()[:50] or None,
            (row.get("land_use") or "").strip()[:200] or None,
            (row.get("occupancy_description") or "").strip()[:200] or None,
            (row.get("resolution_no") or "").strip()[:100] or None,
            (row.get("parent_project_no") or "").strip()[:50] or None,
            _parse_socrata_date(row.get("applied")),
            _parse_socrata_date(row.get("approved")),
            _parse_socrata_date(row.get("closed")),
            _parse_socrata_date(row.get("expired")),
            _parse_socrata_date(row.get("status_date")),
            (row.get("applied_by") or "").strip()[:200] or None,
            (row.get("approved_by") or "").strip()[:200] or None,
            (row.get("applied_affordability_level") or "").strip()[:100] or None,
            (row.get("approved_affordability_level") or "").strip()[:100] or None,
            (row.get("nbrhd_council") or "").strip()[:100] or None,
            _safe_numeric(row.get("latitude")),
            _safe_numeric(row.get("longitude")),
            "socrata_projects",
            socrata_id,
        )

    return _sync_socrata_paginated(
        dataset_key="project_trak",
        city_fips=city_fips,
        process_row=process_row,
        table_name="city_projects",
        conn=conn,
        where=where,
        insert_sql="""INSERT INTO city_projects
            (city_fips, project_no, project_name, project_type, project_subtype,
             description, status, site_address, site_apn, site_zip,
             zoning_code, land_use, occupancy_description,
             resolution_no, parent_project_no,
             applied_date, approved_date, closed_date, expired_date, status_date,
             applied_by, approved_by,
             affordability_level_applied, affordability_level_approved,
             neighborhood_council, latitude, longitude,
             source, socrata_row_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT ON CONSTRAINT uq_city_project
            DO UPDATE SET
                status = EXCLUDED.status,
                approved_date = EXCLUDED.approved_date,
                closed_date = EXCLUDED.closed_date,
                expired_date = EXCLUDED.expired_date,
                status_date = EXCLUDED.status_date,
                approved_by = EXCLUDED.approved_by,
                affordability_level_approved = EXCLUDED.affordability_level_approved,
                updated_at = NOW()
            RETURNING (xmax = 0) AS inserted""",
        source_label="Projects",
    )


def _safe_numeric(val) -> float | None:
    """Safely parse a numeric value from Socrata."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val) -> int | None:
    """Safely parse an integer value from Socrata."""
    if val is None:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def sync_courts(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
    **extra,
) -> dict:
    """Sync court records from Tyler Odyssey portal.

    Searches for officials, donors, and Form 700 filers by name.
    Stores discovered cases and cross-references against known entities.
    """
    from courts_scraper import lookup_entities

    print("  Running court records lookup...")
    result = lookup_entities(city_fips=city_fips)

    return {
        "records_fetched": result.get("names_searched", 0),
        "records_new": result.get("cases_saved", 0),
        "records_updated": result.get("cases_updated", 0),
        "matches_found": result.get("matches_found", 0),
    }


def sync_propublica(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync nonprofit organization data from ProPublica Nonprofit Explorer.

    Resolves donor employers against ProPublica's nonprofit database.
    Creates organization records and entity links for matched nonprofits.
    """
    from propublica_client import batch_resolve_employers
    from db import (
        load_organizations_to_db,
        load_entity_links_to_db,
        resolve_entity_link_ids,
    )

    # 1. Fetch distinct employer names from donors table
    with conn.cursor() as cur:
        cur.execute(
            """SELECT DISTINCT employer FROM donors
               WHERE city_fips = %s
                 AND employer IS NOT NULL
                 AND employer != ''
               ORDER BY employer""",
            (city_fips,),
        )
        employers = [row[0] for row in cur.fetchall()]

    print(f"  Found {len(employers)} distinct employer names to resolve...")

    # 2. Resolve against ProPublica
    matches = batch_resolve_employers(employers, state="CA")
    print(f"  Matched {len(matches)} employers to nonprofits")

    if not matches:
        return {
            "records_fetched": len(employers),
            "records_new": 0,
            "records_updated": 0,
            "entities_resolved": 0,
        }

    # 3. Load matched organizations
    org_records = []
    for m in matches:
        org_records.append({
            "name": m["name"],
            "entity_number": str(m["ein"]),
            "entity_type": "nonprofit",
            "jurisdiction": "US",
            "status": "active" if m.get("has_filings") else None,
            "source": "propublica_990",
            "source_url": f"https://projects.propublica.org/nonprofits/organizations/{m['ein']}",
            "metadata": {
                "ntee_code": m.get("ntee_code"),
                "city": m.get("city"),
                "state": m.get("state"),
                "matched_employer": m.get("matched_employer"),
                "match_confidence": m.get("confidence"),
            },
        })

    org_stats = load_organizations_to_db(conn, org_records, city_fips=city_fips)
    print(f"  Organizations: {org_stats['inserted']} new, {org_stats['updated']} updated")

    # 4. Create entity links (employer name -> organization)
    # The "person" here is the employer name — it links to the org.
    # For ProPublica, we don't have individual officer names from the API.
    # The link represents "this donor works at this nonprofit org."
    link_records = []
    with conn.cursor() as cur:
        for m in matches:
            # Find the organization we just loaded
            cur.execute(
                """SELECT id FROM organizations
                   WHERE city_fips = %s AND source = 'propublica_990'
                     AND entity_number = %s""",
                (city_fips, str(m["ein"])),
            )
            org_row = cur.fetchone()
            if not org_row:
                continue

            # Find donors with this employer
            norm_employer = " ".join(m["matched_employer"].lower().split())
            cur.execute(
                """SELECT DISTINCT name, normalized_name FROM donors
                   WHERE city_fips = %s
                     AND normalized_employer = %s""",
                (city_fips, norm_employer),
            )
            for donor_row in cur.fetchall():
                link_records.append({
                    "person_name": donor_row[0],
                    "organization_id": org_row[0],
                    "role": "employee",
                    "role_detail": f"Employer: {m['matched_employer']}",
                    "confidence": m.get("confidence", 0.80),
                    "source": "propublica_990",
                    "source_url": f"https://projects.propublica.org/nonprofits/organizations/{m['ein']}",
                })

    link_stats = load_entity_links_to_db(conn, link_records, city_fips=city_fips)
    print(f"  Entity links: {link_stats['inserted']} new, {link_stats['updated']} updated")

    # 5. Resolve links to existing donor/official IDs
    resolve_stats = resolve_entity_link_ids(conn, city_fips=city_fips)
    print(f"  Resolved: {resolve_stats['donor_resolved']} donors, {resolve_stats['official_resolved']} officials")

    return {
        "records_fetched": len(employers),
        "records_new": org_stats["inserted"],
        "records_updated": org_stats["updated"],
        "entity_links_created": link_stats["inserted"],
        "entities_resolved": resolve_stats["donor_resolved"] + resolve_stats["official_resolved"],
    }


def sync_form803_behested(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
    **kwargs,
) -> dict:
    """Sync FPPC Form 803 behested payment disclosures.

    Fetches from FPPC portal, loads to behested_payments table.
    """
    from fppc_form803_client import fetch_behested_payments
    from db import load_behested_to_db

    print(f"  Fetching behested payments from FPPC (sync_type={sync_type})...")

    payments = fetch_behested_payments(city_fips=city_fips)
    print(f"  Fetched {len(payments)} behested payment records")

    if not payments:
        return {"records_fetched": 0, "records_new": 0, "records_updated": 0}

    stats = load_behested_to_db(conn, payments, city_fips=city_fips)
    print(f"  Loaded: {stats['loaded']} new, {stats['updated']} updated, {stats['skipped']} skipped")

    return {
        "records_fetched": len(payments),
        "records_new": stats["loaded"],
        "records_updated": stats["updated"],
        "records_skipped": stats["skipped"],
    }


def sync_lobbyist_registrations(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
    **kwargs,
) -> dict:
    """Sync lobbyist registration records.

    Fetches from City Clerk website and optionally CA SOS portal,
    loads to lobbyist_registrations table.
    """
    from lobbyist_client import fetch_lobbyist_registrations
    from db import load_lobbyists_to_db

    print(f"  Fetching lobbyist registrations (sync_type={sync_type})...")

    registrations = fetch_lobbyist_registrations(city_fips=city_fips)
    print(f"  Fetched {len(registrations)} lobbyist registration records")

    if not registrations:
        return {"records_fetched": 0, "records_new": 0, "records_updated": 0}

    stats = load_lobbyists_to_db(conn, registrations, city_fips=city_fips)
    print(f"  Loaded: {stats['loaded']} new, {stats['updated']} updated, {stats['skipped']} skipped")

    return {
        "records_fetched": len(registrations),
        "records_new": stats["loaded"],
        "records_updated": stats["updated"],
        "records_skipped": stats["skipped"],
    }


def sync_opencorporates(
    conn,
    city_fips: str = DEFAULT_FIPS,
    sync_type: str = "incremental",
    **kwargs,
) -> dict:
    """Resolve business entity names from donors against OpenCorporates.

    Finds entity-like donor names (LLC/Inc/Corp/etc), deduplicates,
    and resolves each against the OpenCorporates API with rate limiting.
    Requires OPENCORPORATES_API_TOKEN env var.
    """
    from opencorporates_client import (
        looks_like_entity, resolve_entity, normalize_entity_name,
        RateLimitTracker,
    )

    print(f"[opencorporates] Resolving business entities for {city_fips}...")

    # Find entity-like donor names
    cur = conn.cursor()
    cur.execute(
        """SELECT DISTINCT name FROM donors
           WHERE city_fips = %s AND name IS NOT NULL""",
        (city_fips,),
    )
    all_donors = [row[0] for row in cur.fetchall()]
    entity_names = [n for n in all_donors if looks_like_entity(n)]

    # Deduplicate by normalized name
    seen: dict[str, str] = {}
    for name in entity_names:
        norm = normalize_entity_name(name)
        if norm not in seen:
            seen[norm] = name

    unique_names = list(seen.values())
    print(f"  {len(entity_names)} entity-like donors → {len(unique_names)} unique after normalization")

    # Resolve each against OpenCorporates
    tracker = RateLimitTracker(db_conn=conn)
    resolved = 0
    skipped = 0
    rate_limited = 0

    for name in unique_names:
        allowed, reason = tracker.can_call()
        if not allowed:
            rate_limited += len(unique_names) - resolved - skipped
            print(f"  Rate limit reached: {reason}. {rate_limited} entities queued for next run.")
            break

        result = resolve_entity(
            name, city_fips=city_fips, rate_tracker=tracker, db_conn=conn,
        )
        if result.cached:
            skipped += 1
        elif result.matched:
            resolved += 1
        else:
            skipped += 1

    print(f"  Resolved: {resolved}, Cached: {skipped}, Rate-limited: {rate_limited}")
    print(f"  {tracker.budget_status()}")

    return {
        "records_fetched": len(unique_names),
        "records_new": resolved,
        "records_skipped": skipped,
        "rate_limited": rate_limited,
    }


def sync_elections(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Sync election cycle data by analyzing existing committee/contribution data.

    This is a derived/enrichment sync — it processes data already in the
    database from netfile and calaccess syncs. Should run after those sources.

    Pipeline:
    1. build_candidates_from_committees — extract candidate info from committee names
    2. assign_committees_to_elections — link committees to election cycles
    3. assign_contributions_to_elections — link contributions to election cycles
    """
    from elections_client import run_election_pipeline

    print("  Running election cycle tracking pipeline...")
    stats = run_election_pipeline(conn, city_fips)

    candidates = stats.get("candidates", {})
    contributions = stats.get("contributions", {})

    return {
        "records_fetched": candidates.get("candidates_created", 0) + candidates.get("candidates_updated", 0),
        "records_new": candidates.get("candidates_created", 0),
        "records_updated": candidates.get("candidates_updated", 0),
        "contributions_assigned": contributions.get("total_assigned", 0),
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


def sync_transcript_recaps(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
    **kwargs,
) -> dict:
    """Generate transcript-based recaps for meetings with local transcripts.

    This is a derived/enrichment sync — it processes meetings that have
    a YouTube or Granicus transcript locally but no transcript_recap yet.
    Available immediately after a meeting (YouTube) or days later (Granicus).

    Calls the Claude API to generate narrative recaps from transcript text.
    """
    from generate_transcript_recaps import generate_transcript_recaps

    result = generate_transcript_recaps(conn, city_fips, force=(sync_type == "full"))

    return {
        "records_fetched": result["total"],
        "records_new": result["generated"],
        "records_updated": 0,
        "skipped": result.get("skipped", 0),
        "errors": result.get("errors", 0),
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


# ── Enrichment Sync Functions ─────────────────────────────────
# These follow the same (conn, city_fips, ...) -> dict contract as sync
# sources but process data already in the database. Each detects its own
# new work — idempotent, zero-cost when nothing needs doing.
# See also: sync_meeting_summaries, sync_written_comments (same pattern).


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

    Uses Claude API (~$0.07/meeting). Skips procedural items.
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


def sync_embedding_generation(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
) -> dict:
    """Generate embeddings for content tables missing them.

    Uses OpenAI text-embedding-3-small (~$0.02/M tokens). Idempotent:
    skips rows that already have embeddings.
    """
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
    prompt_path = Path(__file__).parent / "prompts" / "proceeding_type_system.txt"
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
    "transcript_recap_generation": sync_transcript_recaps,
    "comment_summary_generation": sync_comment_summaries,
    "embedding_generation": sync_embedding_generation,
    "proceeding_classification": sync_proceeding_classification,
}


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
                result = sync_fn(**_build_call_args(sync_fn, conn))
                last_error = None
                break  # Success
            except (ConnectionError, TimeoutError, OSError) as e:
                last_error = e
                print(f"\n  Transient error (attempt {attempt + 1}/{max_retries + 1}): {e}")
                if attempt == max_retries:
                    raise  # Final attempt — let outer handler catch it
            except Exception as e:
                # Check for HTTP 5xx or connection-related errors in message
                err_str = str(e).lower()
                if any(kw in err_str for kw in ("500", "502", "503", "504", "timeout", "connection")):
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

        # Check for anomalies in sync results
        check_anomalies(
            journal, conn, city_fips, f"sync_{source}",
            current_count=result.get("records_fetched"),
            current_seconds=execution_time,
            count_metric_key="records_fetched",
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
        conn.close()


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
        "orientation_generation", "recap_generation", "transcript_recap_generation",
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
            "transcript_recap_generation", "comment_summary_generation",
        ]
        print(f"\n{'=' * 60}")
        print(f"  ENRICHMENT SWEEP — running all enrichments with pending work")
        print(f"{'=' * 60}\n")
        any_failed = False
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
            except Exception as e:
                print(f"  ERROR: {e}")
                any_failed = True
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
