"""
escribemeetings pipeline module — extracted from data_sync.py (Phase 2.3).

Each sync_X function is registered in data_sync.SYNC_SOURCES and dispatched
by data_sync.run_sync. Module-level helpers (escribemeetings-specific) live alongside.
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
        # Upcoming 14 days + past 60 days.  The wider backward window
        # catches meetings that were scraped before their agenda was
        # published.  The per-meeting skip check (below) makes this cheap:
        # meetings that already have items are skipped instantly.
        from datetime import timedelta
        today = datetime.now().date()
        cutoff = today + timedelta(days=14)
        lookback = today - timedelta(days=60)
        meetings = [
            m for m in meetings
            if get_meeting_date(m) != "unknown"
            and lookback <= datetime.strptime(get_meeting_date(m), "%Y-%m-%d").date() <= cutoff
        ]

    print(f"  Found {len(meetings)} meetings to process")

    new_count = 0
    skipped_count = 0
    error_count = 0
    errors: list[str] = []

    for i, meeting in enumerate(meetings, 1):
        meeting_date = get_meeting_date(meeting)
        meeting_name = meeting.get("MeetingName", "Unknown")

        # Resolve body early so the skip check can be precise
        body_name = escribemeetings_to_body.get(meeting_name, meeting_name)
        body_id = resolve_body_id(conn, city_fips, body_name)

        # Skip if meeting already has agenda items in Layer 2.
        # This is the single gate: it catches every failure mode —
        # scraped before agenda was published, items dropped during
        # loading, partial extraction, etc.  No document metadata
        # checks, no deletions, just: "does the output exist?"
        with conn.cursor() as cur:
            cur.execute(
                """SELECT 1 FROM agenda_items ai
                   JOIN meetings m ON m.id = ai.meeting_id
                   WHERE m.city_fips = %s AND m.meeting_date = %s
                     AND m.body_id IS NOT DISTINCT FROM %s
                   LIMIT 1""",
                (city_fips, meeting_date, str(body_id) if body_id else None),
            )
            if cur.fetchone():
                skipped_count += 1
                continue

        print(f"  [{i}/{len(meetings)}] Scraping {meeting_date} ({meeting_name})...")
        try:
            data = _scrape_meeting_with_timeout(
                session, meeting, timeout=ESCRIBEMEETINGS_TIMEOUT,
            )
            raw_bytes = json.dumps(data, indent=2).encode("utf-8")
            source_id = f"escribemeetings_{meeting_name}_{meeting_date}"
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


