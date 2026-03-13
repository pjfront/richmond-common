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
  - socrata_payroll: City employee payroll (Socrata open data)
  - socrata_expenditures: City spending records (Socrata open data)

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
    from db import ingest_document, load_meeting_to_db
    from run_pipeline import convert_escribemeetings_to_scanner_format

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

        # Check if we already have this meeting's raw data
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id FROM documents
                   WHERE city_fips = %s AND source_type = 'escribemeetings'
                     AND source_identifier = %s""",
                (city_fips, f"escribemeetings_{meeting_date}"),
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
                source_identifier=f"escribemeetings_{meeting_date}",
                mime_type="application/json",
                metadata={
                    "meeting_date": meeting_date,
                    "meeting_name": data.get("meeting_name"),
                    "item_count": len(data.get("items", [])),
                    "pipeline": "data_sync",
                },
            )

            # Hydrate Layer 2: meetings + agenda_items
            scanner_data = convert_escribemeetings_to_scanner_format(data)
            load_meeting_to_db(
                conn, scanner_data,
                document_id=doc_id, city_fips=city_fips,
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
    from db import load_meeting_to_db

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
            scanner_data = convert_escribemeetings_to_scanner_format(escribemeetings_data)
            load_meeting_to_db(
                conn, scanner_data,
                document_id=doc_id, city_fips=city_fips,
            )
            hydrated += 1
            meeting_date = escribemeetings_data.get("meeting_date", "?")
            items = len(escribemeetings_data.get("items", []))
            print(f"    {meeting_date}: {items} items → Layer 2")
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


# ADIDs that are public comment compilations, not actual minutes.
# Sourced from batch_extract.py — skip these during extraction.
_COMMENT_COMPILATION_ADIDS = {"17313", "17289", "17274", "17234"}


def sync_minutes_extraction(
    conn,
    city_fips: str,
    sync_type: str = "incremental",
    sync_log_id=None,
    limit: int | None = None,
) -> dict:
    """Extract structured meeting data from Archive Center minutes PDFs.

    Reads AMID=31 documents from Layer 1, runs Claude extraction via
    extract_with_tool_use(), records the extraction run, and loads
    structured data into Layer 2 tables (meetings, agenda_items, motions,
    votes, meeting_attendance).

    For incremental: only extracts documents with no current extraction_runs entry.
    For full: re-extracts all AMID=31 documents (marks old runs non-current).
    """
    import time
    from pipeline import extract_with_tool_use
    from db import save_extraction_run, load_meeting_to_db

    city_cfg = get_city_config(city_fips)
    ac_cfg = city_cfg["data_sources"].get("archive_center", {})
    minutes_amid = ac_cfg.get("minutes_amid", 31)

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

    # Filter out known comment compilations
    filtered = []
    for doc_id, metadata in docs:
        adid = str((metadata or {}).get("adid", ""))
        if adid in _COMMENT_COMPILATION_ADIDS:
            continue
        filtered.append((doc_id, metadata))

    skipped = len(docs) - len(filtered)
    if skipped:
        print(f"  Skipped {skipped} comment compilation documents")

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

            data, usage = extract_with_tool_use(raw_text, return_usage=True)

            # Estimate cost (Sonnet input $3/MTok, output $15/MTok)
            cost = (
                usage["input_tokens"] * 3.0 / 1_000_000
                + usage["output_tokens"] * 15.0 / 1_000_000
            )

            save_extraction_run(
                conn,
                document_id=doc_id,
                extracted_data=data,
                model="claude-sonnet-4-20250514",
                prompt_version="extraction_v1",
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                cost_usd=round(cost, 4),
            )

            load_meeting_to_db(
                conn, data,
                document_id=doc_id, city_fips=city_fips,
            )

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

    # Filter comment compilations
    filtered = []
    for doc_id, metadata in docs:
        adid = str((metadata or {}).get("adid", ""))
        if adid in _COMMENT_COMPILATION_ADIDS:
            continue
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

        print(f"    {len(raw_rows)} raw rows → {len(records)} employees")

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

    print(f"  Payroll sync complete: {total_fetched} raw rows → {total_loaded} employees")

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


SYNC_SOURCES = {
    "netfile": sync_netfile,
    "calaccess": sync_calaccess,
    "escribemeetings": sync_escribemeetings,
    "nextrequest": sync_nextrequest,
    "archive_center": sync_archive_center,
    "form700": sync_form700,
    "minutes_extraction": sync_minutes_extraction,
    "socrata_payroll": sync_socrata_payroll,
    "socrata_expenditures": sync_socrata_expenditures,
    "courts": sync_courts,
}


def run_sync(
    source: str,
    city_fips: str = DEFAULT_FIPS,
    sync_type: str = "incremental",
    triggered_by: str = "manual",
    pipeline_run_id: str = None,
    limit: int | None = None,
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

    journal = PipelineJournal(conn, city_fips)
    journal.log_run_start("data_sync", str(sync_log_id),
        f"Sync {source} ({sync_type}, triggered by {triggered_by})",
        {"source": source, "sync_type": sync_type, "triggered_by": triggered_by,
         "pipeline_run_id": pipeline_run_id})

    try:
        sync_fn = SYNC_SOURCES[source]
        extra = {"limit": limit} if source == "minutes_extraction" and limit is not None else {}
        result = sync_fn(conn, city_fips, sync_type, sync_log_id, **extra)

        execution_time = time.time() - start_time
        complete_sync_log(
            conn,
            sync_log_id=sync_log_id,
            records_fetched=result.get("records_fetched"),
            records_new=result.get("records_new"),
            records_updated=result.get("records_updated"),
            metadata={"execution_seconds": round(execution_time, 2), **result},
        )

        journal.log_run_end("data_sync", str(sync_log_id), "completed",
            f"Sync {source} complete in {execution_time:.1f}s", {
                "source": source,
                "records_fetched": result.get("records_fetched", 0),
                "records_new": result.get("records_new", 0),
                "records_updated": result.get("records_updated", 0),
                "execution_seconds": round(execution_time, 2),
            })

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
        description="Richmond Transparency Project — Data Source Sync",
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
    parser.add_argument("--source", choices=list(SYNC_SOURCES), help="Data source to sync")
    parser.add_argument("--sync-type", choices=["full", "incremental"], default="incremental", help="Sync type")
    parser.add_argument("--triggered-by", default="manual", help="What triggered this sync")
    parser.add_argument("--city-fips", default=DEFAULT_FIPS, help="City FIPS code")
    parser.add_argument("--pipeline-run-id", help="GitHub Actions run ID or n8n execution ID")
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
        print("Extracting structured data from Archive Center minutes...")
        conn = get_connection()
        try:
            result = sync_minutes_extraction(
                conn, city_fips=args.city_fips, sync_type=args.sync_type,
                limit=args.limit,
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

    if not args.source:
        parser.error("--source is required (unless using --list-cities)")

    pipeline_run_id = args.pipeline_run_id or os.getenv("GITHUB_RUN_ID")

    result = run_sync(
        source=args.source,
        city_fips=args.city_fips,
        sync_type=args.sync_type,
        triggered_by=args.triggered_by,
        pipeline_run_id=pipeline_run_id,
        limit=args.limit,
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
