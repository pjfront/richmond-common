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


def _strip_public_raw_operational_paths(value):
    """Remove local filesystem implementation details from public raw JSON."""
    if isinstance(value, dict):
        return {
            key: _strip_public_raw_operational_paths(child)
            for key, child in value.items()
            if key not in {"local_path", "text_path"}
        }
    if isinstance(value, list):
        return [_strip_public_raw_operational_paths(child) for child in value]
    return value


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
        fetch_meeting_revision,
        get_meeting_date,
    )
    from db import (
        ingest_document,
        load_meeting_to_db,
        resolve_body_id,
        retire_escribe_agenda,
    )
    from run_pipeline import convert_escribemeetings_to_scanner_format

    city_cfg = get_city_config(city_fips)

    # Build reverse mapping: eSCRIBE MeetingName → canonical body name
    comm_cfg = city_cfg["data_sources"].get("commissions_escribemeetings", {})
    escribemeetings_to_body = {v: k for k, v in comm_cfg.items()}
    escribemeetings_to_body["City Council"] = "City Council"

    session = create_session()

    if sync_type == "full":
        print("  Discovering all meetings from eSCRIBE...")
        meetings = discover_meetings(session, include_cancelled=True)
        # Process newest first: recent meetings are highest value
        meetings.sort(key=lambda m: m.get("StartDate", ""), reverse=True)
    else:
        print("  Checking eSCRIBE for upcoming meetings...")
        meetings = discover_meetings(session, include_cancelled=True)
        # Upcoming 14 days + past 60 days. The wider backward window catches
        # late publication and amendments. A stable upstream revision check
        # below keeps already-current meetings cheap.
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
    updated_count = 0
    skipped_count = 0
    awaiting_agenda_count = 0
    error_count = 0
    errors: list[str] = []

    for i, meeting in enumerate(meetings, 1):
        meeting_date = get_meeting_date(meeting)
        meeting_name = meeting.get("MeetingName", "Unknown")

        try:
            source_observed_at = datetime.now().astimezone().isoformat()
            body_name = escribemeetings_to_body.get(meeting_name, meeting_name)
            body_id = resolve_body_id(conn, city_fips, body_name)
            meeting_guid = str(meeting.get("ID") or "").strip() or None
            meeting_type = (
                "special" if "special" in meeting_name.lower()
                else "regular"
            )
            source_id = (
                f"escribemeetings_{meeting_guid}"
                if meeting_guid
                else f"escribemeetings_{meeting_name}_{meeting_date}"
            )
            revision, meeting_html = fetch_meeting_revision(
                session,
                meeting,
                city_fips=city_fips,
            )
            revision_sha256 = revision["revision_sha256"]

            # A Layer-1 observation is not proof that the structured load
            # succeeded. Only revisions marked after load_meeting_to_db are
            # eligible for the skip, so a crash between the two remains
            # retryable even when older agenda items exist.
            with conn.cursor() as cur:
                cur.execute(
                    """WITH target_meeting AS (
                           SELECT m.id
                           FROM meetings m
                           WHERE m.city_fips = %s
                             AND (
                               (%s IS NOT NULL
                                AND m.source_meeting_guid = %s)
                               OR (
                                 m.meeting_date = %s
                                 AND m.meeting_type = %s
                                 AND m.body_id IS NOT DISTINCT FROM %s
                               )
                             )
                           ORDER BY (
                             %s IS NOT NULL
                             AND m.source_meeting_guid = %s
                           ) DESC
                           LIMIT 1
                         )
                         SELECT
                           (
                             SELECT d.metadata->>'agenda_revision_applied_sha256'
                             FROM documents d
                             WHERE d.city_fips = %s
                               AND d.source_type = 'escribemeetings'
                               AND (
                                 d.source_identifier = %s
                                 OR (%s IS NOT NULL
                                     AND d.metadata->>'meeting_guid' = %s)
                               )
                               AND d.metadata ? 'agenda_revision_applied_sha256'
                               AND d.source_retired_at IS NULL
                               AND COALESCE(
                                 d.metadata->>'raw_sanitized', 'false'
                               ) = 'true'
                             ORDER BY d.ingested_at DESC
                             LIMIT 1
                           ) AS applied_revision,
                           EXISTS (
                             SELECT 1 FROM agenda_items ai
                             JOIN target_meeting tm ON tm.id = ai.meeting_id
                             WHERE ai.agenda_source_retired_at IS NULL
                           ) AS has_items,
                           EXISTS (
                             SELECT 1
                             FROM target_meeting tm
                             JOIN meetings m ON m.id = tm.id
                             LEFT JOIN documents md ON md.id = m.document_id
                             WHERE (
                                 md.source_type = 'archive_center'
                                 OR EXISTS (
                                   SELECT 1
                                   FROM agenda_items ai
                                   WHERE ai.meeting_id = m.id
                                     AND ai.agenda_source_authority = 'minutes'
                                 )
                                 OR EXISTS (
                                   SELECT 1
                                   FROM agenda_items ai
                                   JOIN motions mo ON mo.agenda_item_id = ai.id
                                   WHERE ai.meeting_id = m.id
                                     AND mo.source = 'minutes'
                                 )
                               )
                           ) AS official_minutes_loaded,
                           EXISTS (
                             SELECT 1 FROM agenda_items ai
                             JOIN target_meeting tm ON tm.id = ai.meeting_id
                             WHERE ai.agenda_source_authority = 'agenda'
                           ) AS has_managed_agenda,
                           (
                             SELECT d.metadata->>'agenda_revision_applied_at'
                             FROM documents d
                             WHERE d.city_fips = %s
                               AND d.source_type = 'escribemeetings'
                               AND d.source_retired_at IS NULL
                               AND COALESCE(
                                 d.metadata->>'raw_sanitized', 'false'
                               ) = 'true'
                               AND (
                                 d.source_identifier = %s
                                 OR (%s IS NOT NULL
                                     AND d.metadata->>'meeting_guid' = %s)
                               )
                             ORDER BY d.ingested_at DESC
                             LIMIT 1
                           ) AS applied_at""",
                    (
                        city_fips,
                        meeting_guid,
                        meeting_guid,
                        meeting_date,
                        meeting_type,
                        str(body_id) if body_id else None,
                        meeting_guid,
                        meeting_guid,
                        city_fips,
                        source_id,
                        meeting_guid,
                        meeting_guid,
                        city_fips,
                        source_id,
                        meeting_guid,
                        meeting_guid,
                    ),
                )
                state = cur.fetchone()
            if isinstance(state, (tuple, list)) and len(state) >= 2:
                applied_revision, has_items = state[0], bool(state[1])
                official_minutes_loaded = (
                    bool(state[2]) if len(state) >= 3 else False
                )
                has_managed_agenda = (
                    bool(state[3]) if len(state) >= 4 else False
                )
                attachment_verification_due = False
                if len(state) >= 5 and state[4]:
                    try:
                        applied_at = datetime.fromisoformat(str(state[4]))
                        if applied_at.tzinfo is None:
                            applied_at = applied_at.astimezone()
                        attachment_verification_due = (
                            datetime.now().astimezone() - applied_at
                        ).total_seconds() >= 86400
                    except (TypeError, ValueError):
                        attachment_verification_due = True
            else:
                # A missing/malformed state cannot authorize a freshness skip.
                applied_revision, has_items = None, False
                official_minutes_loaded = False
                has_managed_agenda = False
                attachment_verification_due = False

            agenda_withdrawn = (
                meeting.get("HasAgenda") is False
                or meeting.get("IsCancelled") is True
            )
            if agenda_withdrawn:
                if applied_revision == revision_sha256:
                    skipped_count += 1
                    continue
                if (
                    not applied_revision
                    and not has_managed_agenda
                    and meeting.get("IsCancelled") is not True
                ):
                    awaiting_agenda_count += 1
                    continue

                print(
                    f"  [{i}/{len(meetings)}] Retiring withdrawn agenda "
                    f"for {meeting_date} ({meeting_name})..."
                )
                withdrawal_url = (
                    "https://pub-richmond.escribemeetings.com/"
                    f"Meeting.aspx?Id={meeting.get('ID')}&Agenda=Agenda&lang=English"
                )
                raw_bytes = json.dumps(_strip_public_raw_operational_paths({
                    "meeting": meeting,
                    "agenda_withdrawn": True,
                    "meeting_cancelled": bool(meeting.get("IsCancelled")),
                    "observed_at": datetime.now().isoformat(),
                }), indent=2).encode("utf-8")
                doc_id = ingest_document(
                    conn,
                    city_fips=city_fips,
                    source_type="escribemeetings",
                    raw_content=raw_bytes,
                    credibility_tier=1,
                    source_url=withdrawal_url,
                    source_identifier=source_id,
                    mime_type="application/json",
                    metadata={
                        "meeting_date": meeting_date,
                        "meeting_name": meeting_name,
                        "item_count": 0,
                        "meeting_guid": meeting.get("ID"),
                        "raw_sanitized": True,
                        "raw_sanitization_version": 1,
                        "agenda_withdrawn": True,
                        "meeting_cancelled": bool(meeting.get("IsCancelled")),
                        "agenda_revision_sha256": revision_sha256,
                        "agenda_revision_observed_at": source_observed_at,
                        "calendar_sha256": revision.get("calendar_sha256"),
                        "pipeline": "data_sync",
                    },
                    commit=False,
                )
                retired_count, minutes_fenced = retire_escribe_agenda(
                    conn,
                    city_fips=city_fips,
                    meeting_date=meeting_date,
                    meeting_type=meeting_type,
                    body_id=body_id,
                    agenda_revision_sha256=revision_sha256,
                    meeting_cancelled=bool(meeting.get("IsCancelled")),
                    source_meeting_guid=meeting_guid,
                    source_observed_at=source_observed_at,
                    commit=False,
                )
                with conn.cursor() as cur:
                    cur.execute(
                        """UPDATE documents
                           SET metadata = COALESCE(metadata, '{}'::jsonb)
                             || %s::jsonb,
                               source_identifier = %s
                           WHERE id = %s""",
                        (
                            json.dumps({
                                "agenda_revision_applied_sha256": (
                                    revision_sha256
                                ),
                                "agenda_revision_applied_at": (
                                    datetime.now().isoformat()
                                ),
                                "agenda_revision_observed_at": (
                                    source_observed_at
                                ),
                                "agenda_items_retired": retired_count,
                                "meeting_guid": meeting_guid,
                                "raw_sanitized": True,
                                "raw_sanitization_version": 1,
                                "agenda_layer2_skipped_for_official_minutes": (
                                    minutes_fenced
                                ),
                            }),
                            source_id,
                            doc_id,
                        ),
                    )
                    cur.execute(
                        """UPDATE documents
                           SET source_retired_at = CASE WHEN id = %s
                             THEN NULL ELSE COALESCE(source_retired_at, NOW()) END
                           WHERE city_fips = %s
                             AND source_type = 'escribemeetings'
                             AND (
                               source_identifier = %s
                               OR (%s IS NOT NULL
                                   AND metadata->>'meeting_guid' = %s)
                             )""",
                        (
                            doc_id, city_fips, source_id,
                            meeting_guid, meeting_guid,
                        ),
                    )
                conn.commit()
                updated_count += 1
                continue
            if (
                applied_revision == revision_sha256
                and has_items
                and (has_managed_agenda or official_minutes_loaded)
                and not attachment_verification_due
            ):
                skipped_count += 1
                continue

            print(
                f"  [{i}/{len(meetings)}] Reconciling {meeting_date} "
                f"({meeting_name})..."
            )
            data = _scrape_meeting_with_timeout(
                session,
                meeting,
                timeout=ESCRIBEMEETINGS_TIMEOUT,
                meeting_html=meeting_html,
                city_fips=city_fips,
            )
            if not data.get("items"):
                raise ValueError(
                    "eSCRIBE reports an agenda but the parsed page contained "
                    "no agenda items"
                )
            scrape_stats = data.get("stats") or {}
            declared_attachments = int(
                scrape_stats.get("total_attachments") or 0
            )
            downloaded_attachments = int(
                scrape_stats.get("downloaded_attachments") or 0
            )
            if downloaded_attachments != declared_attachments:
                raise RuntimeError(
                    "eSCRIBE attachment set is incomplete: "
                    f"{downloaded_attachments}/{declared_attachments} downloaded"
                )
            raw_bytes = json.dumps(
                _strip_public_raw_operational_paths(data), indent=2
            ).encode("utf-8")
            doc_id = ingest_document(
                conn,
                city_fips=city_fips,
                source_type="escribemeetings",
                raw_content=raw_bytes,
                credibility_tier=1,
                source_url=data.get("portal_url") or data.get("meeting_url"),
                source_identifier=source_id,
                mime_type="application/json",
                metadata={
                    "meeting_date": meeting_date,
                    "meeting_name": data.get("meeting_name"),
                    "item_count": len(data.get("items", [])),
                    "meeting_guid": meeting.get("ID"),
                    "raw_sanitized": True,
                    "raw_sanitization_version": 1,
                    "agenda_revision_sha256": revision_sha256,
                    "agenda_revision_observed_at": source_observed_at,
                    "agenda_html_sha256": revision.get("agenda_sha256"),
                    "calendar_sha256": revision.get("calendar_sha256"),
                    "pipeline": "data_sync",
                },
                commit=False,
            )

            # Reconcile every complete agenda revision. Per-row minutes
            # authority fences adopted outcomes while still allowing mutable
            # agenda-only rows and attachments to be corrected or retracted.
            scanner_data = convert_escribemeetings_to_scanner_format(data)
            load_meeting_to_db(
                conn, scanner_data,
                document_id=doc_id, city_fips=city_fips,
                body_id=body_id,
                agenda_url=data.get("portal_url"),
                authoritative_agenda_revision=revision_sha256,
                source_meeting_guid=meeting_guid,
                source_observed_at=source_observed_at,
                commit=False,
            )
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE documents
                       SET metadata = COALESCE(metadata, '{}'::jsonb)
                         || %s::jsonb,
                           source_identifier = %s
                       WHERE id = %s""",
                    (
                        json.dumps({
                            "agenda_revision_applied_sha256": revision_sha256,
                            "agenda_revision_applied_at": datetime.now().isoformat(),
                            "agenda_revision_observed_at": source_observed_at,
                            "meeting_guid": meeting_guid,
                            "raw_sanitized": True,
                            "raw_sanitization_version": 1,
                            "agenda_minutes_rows_preserved": (
                                official_minutes_loaded
                            ),
                        }),
                        source_id,
                        doc_id,
                    ),
                )
                cur.execute(
                    """UPDATE documents
                       SET source_retired_at = CASE WHEN id = %s
                         THEN NULL ELSE COALESCE(source_retired_at, NOW()) END
                       WHERE city_fips = %s
                         AND source_type = 'escribemeetings'
                         AND (
                           source_identifier = %s
                           OR (%s IS NOT NULL
                               AND metadata->>'meeting_guid' = %s)
                         )""",
                    (
                        doc_id, city_fips, source_id,
                        meeting_guid, meeting_guid,
                    ),
                )
            conn.commit()
            if has_items or applied_revision:
                updated_count += 1
            else:
                new_count += 1
        except Exception as e:
            conn.rollback()
            error_count += 1
            error_msg = f"{meeting_date}: {e}"
            errors.append(error_msg)
            print(f"    ERROR: {e}")

        # Update sync log progress after each meeting (if we have a log ID)
        if sync_log_id and (new_count + updated_count + error_count) % 5 == 0:
            _update_sync_progress(conn, sync_log_id, {
                "processed": i,
                "total": len(meetings),
                "new": new_count,
                "updated": updated_count,
                "skipped": skipped_count,
                "errors": error_count,
                "last_date": meeting_date,
            })

    return {
        "records_fetched": len(meetings),
        "records_new": new_count,
        "records_updated": updated_count,
        "skipped": skipped_count,
        "awaiting_agenda": awaiting_agenda_count,
        "errors": error_count,
        "error_details": errors[:10],  # Cap at 10 to keep metadata manageable
        # A per-meeting exception is intentionally soft inside this source so
        # the remaining meetings still load. The durable change-event runner
        # uses this explicit contract to retry instead of terminally acking
        # the partial source result; ordinary scheduled/manual runs remain
        # best-effort and retain status=completed.
        "retryable_incomplete": error_count > 0,
        "incomplete_count": error_count,
        "incomplete_reasons": (
            [f"{error_count} eSCRIBE meeting(s) failed to sync"]
            if error_count
            else []
        ),
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

    # Determine scan start for incremental mode.
    # Query meetings.minutes_url for the highest known Post-Meeting Minutes
    # DocumentId — NOT documents.metadata (agenda attachments). Post-Meeting
    # Minutes are standalone documents whose IDs race ahead of what meeting
    # pages reference; anchoring start_doc_id on agenda attachment IDs leaves
    # the scan window too narrow and silently misses newly posted minutes.
    start_doc_id = 55000  # Known earliest Post-Meeting Minutes
    if sync_type == "incremental":
        with conn.cursor() as cur:
            cur.execute(
                """SELECT MAX(doc_id::int) FROM (
                       SELECT (regexp_match(minutes_url, 'DocumentId=([0-9]+)', 'i'))[1] AS doc_id
                       FROM meetings
                       WHERE city_fips = %s
                         AND minutes_url LIKE '%%escribemeetings%%filestream%%'
                   ) sub WHERE doc_id IS NOT NULL""",
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
    session,
    meeting: dict,
    timeout: int = 300,
    meeting_html: str | None = None,
    city_fips: str | None = None,
) -> dict:
    """Wrapper around scrape_meeting with a per-meeting timeout.

    Uses threading to enforce the timeout since signal-based timeouts
    don't work reliably in all environments (e.g., non-main threads).
    """
    from escribemeetings_scraper import scrape_meeting
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            scrape_meeting,
            session,
            meeting,
            meeting_html=meeting_html,
            city_fips=city_fips,
        )
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
    """Disabled: historic raw revisions lack current attachment proof.

    Use ``data_sync.py --source escribemeetings --sync-type full`` so the
    upstream GUID, current HTML, attachment bytes, and sanitization proof are
    re-observed together. Replaying arbitrary Layer-1 revisions can publish a
    stale agenda and is intentionally no longer supported.
    """
    raise RuntimeError(
        "Legacy eSCRIBE Layer-2 backfill is disabled; run a full source sync"
    )



# Structural markers that distinguish actual meeting minutes from
# public-comment-only documents. Phase 2.3 split misplaced this constant
# in form700.py (where it's unused); the function below is the only
# real consumer. Restored at module scope here 2026-05-17.
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
                model="deepseek-v4-pro",
                prompt_version=prompt_ver,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                cost_usd=round(cost, 4),
                commit=False,
            )

            load_meeting_to_db(
                conn, data,
                document_id=doc_id, city_fips=city_fips,
                body_id=body_id,
                official_minutes=True,
                commit=False,
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
            model="deepseek-v4-pro",
            prompt_version="extraction_v1_batch",
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cost_usd=round(cost, 4),
            commit=False,
        )

        try:
            load_meeting_to_db(
                conn, data,
                document_id=doc_id, city_fips=city_fips,
                official_minutes=True,
                commit=False,
            )
            conn.commit()
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

    # Record batch spend in pipeline_journal. The synchronous Messages.create
    # gate can't see batch spend (async results), so without this the monthly
    # cap + cost digest silently undercount the weekly minutes extraction —
    # the single largest scheduled API job. caller is set explicitly because
    # _detect_caller would attribute to this pipelines.escribemeetings frame,
    # which is the correct owner, but pinning it keeps the digest label stable.
    if total_input_tokens or total_output_tokens:
        try:
            import llm_budget_lock
            llm_budget_lock.log_batch_cost(
                model="deepseek-v4-pro",
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                caller="minutes_extraction",
                batch_id=batch_id,
            )
        except Exception:
            pass

    return {
        "records_new": extracted,
        "errors": errors,
        "error_details": error_details[:10],
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_cost_usd": round(total_cost, 2),
    }


