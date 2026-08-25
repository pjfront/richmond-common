"""Focused regressions for source revisions missed by count/date cursors."""
from __future__ import annotations

import hashlib
import json
import re
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import change_detector
import pytest
from source_fingerprints import escribe_agenda_html_sha256


ROOT = Path(__file__).resolve().parent.parent


class _Response:
    def __init__(self, body: bytes):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_escribe_agenda_hash_ignores_transport_nonces_but_not_content():
    volatile_a = """
      <a href="https://x/cdn-cgi/content?id=nonce-a" aria-hidden="true"></a>
      <input type="hidden" name="__VIEWSTATE" value="signed-a">
      <a href="/cdn-cgi/l/email-protection#abcdef">
        <span data-cfemail="abcdef">[email protected]</span>
      </a>
      <div class="AgendaItemTitle">Approve contract A</div>
    """
    volatile_b = """
      <a href="https://x/cdn-cgi/content?id=nonce-b" aria-hidden="true"></a>
      <input type="hidden" name="__VIEWSTATE" value="signed-b">
      <a href="/cdn-cgi/l/email-protection#123456">
        <span data-cfemail="123456">[email protected]</span>
      </a>
      <div class="AgendaItemTitle">Approve contract A</div>
    """
    amended = volatile_b.replace("contract A", "amended contract B")

    assert escribe_agenda_html_sha256(volatile_a) == escribe_agenda_html_sha256(
        volatile_b
    )
    assert escribe_agenda_html_sha256(volatile_b) != escribe_agenda_html_sha256(
        amended
    )


def test_escribe_watcher_revision_changes_when_known_agenda_is_amended(monkeypatch):
    meeting = {
        "ID": "meeting-guid",
        "MeetingName": "City Council",
        "StartDate": "2026/08/18 18:30:00",
        "EndDate": "2026/08/18 23:00:00",
        "HasAgenda": True,
        "MeetingDocumentLink": [{
            "Type": "Agenda",
            "Format": ".pdf",
            "Title": "Agenda (PDF)",
            "Url": "/FileStream.ashx?DocumentId=70001",
        }],
    }
    page = {"html": "<div class='AgendaItemTitle'>Original item</div>"}

    class _Opener:
        def open(self, request, timeout=15):
            if getattr(request, "data", None):
                return _Response(json.dumps({"d": [meeting]}).encode())
            if "Meeting.aspx?" in request.full_url:
                return _Response(page["html"].encode())
            return _Response(b"")

    monkeypatch.setattr(
        change_detector.urllib.request,
        "build_opener",
        lambda *_args, **_kwargs: _Opener(),
    )

    first = change_detector.check_escribemeetings()
    page["html"] = "<div class='AgendaItemTitle'>Amended item</div>"
    second = change_detector.check_escribemeetings()

    assert first["meeting_count"] == second["meeting_count"] == 1
    assert first["meeting_keys"] == second["meeting_keys"]
    assert first["meeting_revisions"] != second["meeting_revisions"]


def test_nextrequest_watcher_detects_same_count_status_and_document_changes(
    monkeypatch,
):
    state = {"status": "In Progress", "document_title": "Initial response.pdf"}

    def _get(url, **_kwargs):
        if "/client/documents?" in url:
            return json.dumps({
                "total_count": 99,
                "documents": [{
                    "id": 9001,
                    "pretty_id": "24-900",
                    "created_at": "08/05/2026",
                    "title": state["document_title"],
                    "state": "public",
                    "redacted_at": None,
                    "doc_date": None,
                }],
            }).encode()
        return json.dumps({
            "total_count": 1200,
            "requests": [{
                "id": "24-900",
                "request_state": state["status"],
                "request_date": "10/01/2024",
                "due_date": None,
                "department_names": "City Clerk",
                "request_text": "Records request",
                "visibility": "Published",
            }],
        }).encode()

    monkeypatch.setattr(change_detector, "_get", _get)
    first = change_detector.check_nextrequest()
    state["status"] = "Closed"
    status_changed = change_detector.check_nextrequest()
    state["document_title"] = "Amended response.pdf"
    document_changed = change_detector.check_nextrequest()

    assert first["total_count"] == status_changed["total_count"] == 1200
    assert first["recent_requests_hash"] != status_changed["recent_requests_hash"]
    assert (
        status_changed["recent_documents_hash"]
        != document_changed["recent_documents_hash"]
    )


def test_nextrequest_watcher_hashes_are_stable_across_tied_row_order(
    monkeypatch,
):
    request_rows = [
        {
            "id": "26-101",
            "request_state": "Open",
            "request_date": "08/20/2026",
        },
        {
            "id": "26-102",
            "request_state": "Open",
            "request_date": "08/20/2026",
        },
    ]
    document_rows = [
        {"id": 9001, "pretty_id": "26-101", "created_at": "08/20/2026"},
        {"id": 9002, "pretty_id": "26-102", "created_at": "08/20/2026"},
    ]
    reverse = {"value": False}

    def _get(url, **_kwargs):
        rows = document_rows if "/client/documents?" in url else request_rows
        ordered = list(reversed(rows)) if reverse["value"] else rows
        return json.dumps({
            "total_count": len(rows),
            "documents" if "/client/documents?" in url else "requests": ordered,
        }).encode()

    monkeypatch.setattr(change_detector, "_get", _get)
    first = change_detector.check_nextrequest()
    reverse["value"] = True
    second = change_detector.check_nextrequest()

    assert first == second


def test_changed_existing_escribe_revision_is_reconciled_without_deletion():
    from pipelines.escribemeetings import sync_escribemeetings

    meeting = {
        "ID": "meeting-guid",
        "MeetingName": "City Council",
        "StartDate": "2026/08/18 18:30:00",
        "HasAgenda": True,
    }
    revision = {
        "revision_sha256": "new-revision",
        "agenda_sha256": "new-agenda",
        "calendar_sha256": "calendar",
    }
    scraped = {
        "meeting_date": "2026-08-18",
        "meeting_name": "City Council",
        "portal_url": "https://example.test/agenda",
        "items": [{"item_number": "V.1", "title": "Amended item"}],
    }
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = ("old-revision", True)
    scrape = MagicMock(return_value=scraped)
    ingest = MagicMock(return_value=uuid.uuid4())
    load = MagicMock(return_value=uuid.uuid4())

    with patch("escribemeetings_scraper.create_session", return_value=MagicMock()), \
         patch("escribemeetings_scraper.discover_meetings", return_value=[meeting]), \
         patch(
             "escribemeetings_scraper.fetch_meeting_revision",
             return_value=(revision, "<html>amended</html>"),
         ), \
         patch("escribemeetings_scraper.scrape_meeting", scrape), \
         patch("db.resolve_body_id", return_value=None), \
         patch("db.ingest_document", ingest), \
         patch("db.load_meeting_to_db", load), \
         patch(
             "run_pipeline.convert_escribemeetings_to_scanner_format",
             return_value={"meeting_date": "2026-08-18", "action_items": []},
         ):
        result = sync_escribemeetings(
            conn, "0660620", sync_type="full", limit=1
        )

    assert result["records_new"] == 0
    assert result["records_updated"] == 1
    assert result["skipped"] == 0
    scrape.assert_called_once()
    load.assert_called_once()
    all_sql = "\n".join(call.args[0] for call in cursor.execute.call_args_list)
    assert "DELETE FROM agenda_items" not in all_sql
    assert "agenda_revision_applied_sha256" in all_sql


def test_nextrequest_old_document_request_is_targeted_and_updated(monkeypatch):
    from pipelines import nextrequest as pipeline

    base = {
        "requests": [],
        "stats": {
            "total_found": 0,
            "details_scraped": 0,
            "documents_found": 0,
            "failure_count": 0,
            "failed_request_ids": [],
            "failure_counts": {},
            "failures": [],
        },
    }
    old_request = {
        "request_number": "24-900",
        "request_text": "Old request with a new response",
        "status": "Closed",
        "documents": [{
            "source_document_id": 9001,
            "filename": "New response.pdf",
            "file_type": "pdf",
            "download_url": "https://example.test/new-response.pdf",
            "released_date": "2026-08-05",
        }],
        "_incomplete_stages": [],
    }
    targeted = MagicMock(return_value={
        "requests": [old_request],
        "stats": {
            "failures": [],
            "failure_count": 0,
            "failed_request_ids": [],
        },
    })
    save = MagicMock(return_value={
        "requests_inserted": 0,
        "requests_updated": 1,
        "documents_inserted": 1,
        "documents_skipped_existing": 0,
    })
    monkeypatch.setitem(sys.modules, "nextrequest_scraper", SimpleNamespace(
        scrape_all=MagicMock(return_value=base),
        list_recent_document_request_ids=lambda **_kwargs: ["24-900"],
        scrape_request_ids=targeted,
        save_to_db=save,
    ))
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (None,)
    cursor.fetchall.return_value = []

    result = pipeline.sync_nextrequest(conn, "0660620", sync_type="incremental")

    assert result["records_updated"] == 1
    targeted.assert_called_once_with(
        ["24-900"], city_fips="0660620", include_documents=True
    )
    assert save.call_args.args[1]["requests"][0]["request_number"] == "24-900"


def test_nextrequest_document_identity_migration_is_exact_and_typed():
    source = ROOT / "src" / "migrations" / "132_nextrequest_document_source_ids.sql"
    mirror = (
        ROOT
        / "supabase"
        / "migrations"
        / "20260807013200_nextrequest_document_source_ids.sql"
    )
    sql = source.read_text(encoding="utf-8")
    assert source.read_bytes() == mirror.read_bytes()
    assert "ADD COLUMN IF NOT EXISTS source_document_id BIGINT" in sql
    assert "uq_nextrequest_documents_source_id" in sql
    assert "WHERE source_document_id IS NOT NULL" in sql
    types = (ROOT / "web" / "src" / "lib" / "database.types.ts").read_text(
        encoding="utf-8"
    )
    assert "source_document_id: number | null" in types


def test_three_revision_invalidation_does_not_reinvalidate_old_tombstones():
    """R1 -> R2 retirement is charged once, not on every later revision."""
    from db.meetings import (
        _active_agenda_revision_changed,
        _agenda_reconciliation_invalidation_ids,
    )

    active_item = uuid.uuid4()
    retired_in_r2 = uuid.uuid4()

    r2_changed = _active_agenda_revision_changed(
        [("agenda", "r1"), ("agenda", "r1")], "r2"
    )
    r2_ids = _agenda_reconciliation_invalidation_ids(
        [], [retired_in_r2], [active_item],
        agenda_revision_changed=r2_changed,
    )
    assert set(r2_ids) == {active_item, retired_in_r2}

    # The R2 tombstone is absent from the active-row comparison and active-ID
    # input when R3 arrives. Only the still-published item is regenerated.
    r3_changed = _active_agenda_revision_changed(
        [("agenda", "r2")], "r3"
    )
    r3_ids = _agenda_reconciliation_invalidation_ids(
        [], [], [active_item], agenda_revision_changed=r3_changed
    )
    assert r3_ids == [active_item]
    assert retired_in_r2 not in r3_ids

    # The 24-hour verification of unchanged R3 has no work. A stale R2
    # tombstone cannot make the revision look changed because the DB query
    # supplies only active rows to this comparison.
    unchanged_r3 = _active_agenda_revision_changed(
        [("agenda", "r3")], "r3"
    )
    assert _agenda_reconciliation_invalidation_ids(
        [], [], [], agenda_revision_changed=unchanged_r3
    ) == []


def test_authoritative_loader_accepts_downloaded_attachment_without_text():
    """A valid non-text/scanned attachment remains publishable as NULL text."""
    from db.meetings import load_meeting_to_db

    meeting_id = uuid.uuid4()
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = (meeting_id,)
    cur.fetchall.return_value = []
    data = {
        "meeting_date": "2026-08-18",
        "meeting_type": "regular",
        "members_present": [],
        "members_absent": [],
        "action_items": [{
            "item_number": "VII.1",
            "title": "Approve source document",
            "description": "The source attachment has no text layer.",
            "attachments": [{
                "document_id": "70001",
                "filename": "scanned-staff-report.pdf",
                "source_url": "https://example.test/70001",
                "source_content_sha256": "a" * 64,
                "extracted_text": "   ",
            }],
        }],
    }

    with patch("db.officials._resolve_body_type", return_value="council"):
        load_meeting_to_db(
            conn,
            data,
            city_fips="0660620",
            body_id=uuid.uuid4(),
            authoritative_agenda_revision="r1",
        )

    attachment_insert = next(
        call for call in cur.execute.call_args_list
        if "INSERT INTO agenda_item_attachments" in call.args[0]
    )
    params = attachment_insert.args[1]
    assert params[4] is None  # extracted_text
    assert params[5] is None  # char_count
    revision_query = next(
        call.args[0] for call in cur.execute.call_args_list
        if "agenda_source_revision_sha256" in call.args[0]
        and "FROM agenda_items ai" in call.args[0]
    )
    assert "agenda_source_retired_at IS NULL" in revision_query


def test_authoritative_loader_does_not_adopt_same_document_unowned_attachment():
    """A NULL-revision same-DocumentId row remains outside eSCRIBE ownership."""
    from db.meetings import load_meeting_to_db

    meeting_id = uuid.uuid4()
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = (meeting_id,)
    # The exact-document lookup represents no managed match. A real
    # NULL-revision row is excluded by the ownership predicate asserted below.
    cur.fetchall.return_value = []
    data = {
        "meeting_date": "2026-08-18",
        "meeting_type": "regular",
        "members_present": [],
        "members_absent": [],
        "action_items": [{
            "item_number": "VII.1",
            "title": "Approve source document",
            "description": "Do not adopt an unowned historical packet.",
            "attachments": [{
                "document_id": "70001",
                "filename": "staff-report.pdf",
                "source_url": "https://example.test/70001",
                "source_content_sha256": "a" * 64,
                "extracted_text": "Current source text",
            }],
        }],
    }

    with patch("db.officials._resolve_body_type", return_value="council"):
        load_meeting_to_db(
            conn,
            data,
            city_fips="0660620",
            body_id=uuid.uuid4(),
            authoritative_agenda_revision="r1",
        )

    exact_lookup = next(
        call.args[0]
        for call in cur.execute.call_args_list
        if "SELECT source_content_sha256" in call.args[0]
    )
    exact_update = next(
        call.args[0]
        for call in cur.execute.call_args_list
        if "UPDATE agenda_item_attachments" in call.args[0]
        and "SET filename" in call.args[0]
    )
    assert "source_revision_sha256 IS NOT NULL" in exact_lookup
    assert "source_revision_sha256 IS NOT NULL" in exact_update
    assert any(
        "INSERT INTO agenda_item_attachments" in call.args[0]
        for call in cur.execute.call_args_list
    )


def test_withdrawal_preserves_unproven_legacy_and_minutes_attachments():
    from db.meetings import retire_escribe_agenda

    meeting_id = uuid.uuid4()
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.side_effect = [
        (meeting_id, True),
        (True,),
    ]
    cur.fetchall.side_effect = [
        [],  # NULL-revision legacy/minutes attachments are outside ownership
        [],  # no agenda-owned rows
    ]

    result = retire_escribe_agenda(
        conn,
        city_fips="0660620",
        meeting_date="2026-08-18",
        meeting_type="regular",
        body_id=uuid.uuid4(),
        agenda_revision_sha256="withdrawn-r2",
    )

    assert result == (0, True)
    attachment_retirement = next(
        call for call in cur.execute.call_args_list
        if "UPDATE agenda_item_attachments aia" in call.args[0]
    )
    assert "aia.source_retired_at IS NULL" in attachment_retirement.args[0]
    assert (
        "aia.source_revision_sha256 IS NOT NULL"
        in attachment_retirement.args[0]
    )
    assert "ai.agenda_source_authority = 'agenda'" in attachment_retirement.args[0]
    assert "RETURNING aia.agenda_item_id" in attachment_retirement.args[0]
    executed_sql = "\n".join(
        call.args[0] for call in cur.execute.call_args_list
    )
    assert "DELETE FROM agenda_items_embeddings" not in executed_sql
    assert "SET plain_language_summary = NULL" not in executed_sql


def test_all_authoritative_attachment_omissions_require_managed_revision():
    """NULL-revision rows never become implicit omission candidates."""
    source = (ROOT / "src" / "db" / "meetings.py").read_text(
        encoding="utf-8"
    )
    retirement_blocks = re.findall(
        r"UPDATE agenda_item_attachments(?:\s+aia)?.*?RETURNING agenda_item_id",
        source,
        flags=re.DOTALL,
    )
    assert retirement_blocks
    assert all(
        "source_revision_sha256 IS NOT NULL" in block
        for block in retirement_blocks
    )


def test_authoritative_attachment_reconciliation_fences_minutes_parents():
    """Every meeting-wide attachment mutation is agenda-authority scoped."""
    source = (ROOT / "src" / "db" / "meetings.py").read_text(
        encoding="utf-8"
    )
    meeting_wide_blocks = re.findall(
        r"UPDATE agenda_item_attachments\s+aia.*?RETURNING aia\.agenda_item_id",
        source,
        flags=re.DOTALL,
    )
    assert meeting_wide_blocks
    assert all(
        "ai.agenda_source_authority = 'agenda'" in block
        for block in meeting_wide_blocks
    )
    exact_parent_lookup = re.search(
        r"SELECT id\s+FROM agenda_items\s+WHERE meeting_id = %s\s+"
        r"AND item_number = %s.*?agenda_source_retired_at IS NULL",
        source,
        flags=re.DOTALL,
    )
    assert exact_parent_lookup
    assert "agenda_source_authority = 'agenda'" in exact_parent_lookup.group(0)


def test_scraper_tracks_nontext_and_scanned_attachment_outcomes(tmp_path):
    import escribemeetings_scraper as scraper

    parsed = {
        "title": "City Council",
        "total_items": 1,
        "total_attachments": 4,
        "items": [{
            "item_number": "VII.1",
            "title": "Source packet",
            "description": "Three valid downloaded formats",
            "attachments": [
                {"document_id": "1", "name": "Word", "url": "word"},
                {"document_id": "2", "name": "Image", "url": "image"},
                {"document_id": "3", "name": "Scan", "url": "scan"},
                {"document_id": "4", "name": "Broken text", "url": "bad"},
            ],
        }],
    }
    suffixes = {
        "1": ".docx",
        "2": ".png",
        "3": ".pdf",
        "4": ".pdf",
    }

    def fake_download(_session, doc_id, output_dir, *_args, **_kwargs):
        path = output_dir / f"document-{doc_id}{suffixes[doc_id]}"
        path.write_bytes(f"downloaded-{doc_id}".encode())
        return path

    with patch.object(scraper, "parse_meeting_page", return_value=parsed), \
         patch.object(scraper, "download_attachment", side_effect=fake_download), \
         patch.object(
             scraper,
             "extract_text_from_pdf",
             side_effect=["", "[Error extracting text: local path omitted]"],
         ), \
         patch.object(scraper.time, "sleep"):
        result = scraper.scrape_meeting(
            MagicMock(),
            {
                "ID": "meeting-guid",
                "MeetingName": "City Council",
                "StartDate": "2026/08/18 18:30:00",
            },
            output_dir=tmp_path / "meeting",
            meeting_html="<html></html>",
        )

    attachments = result["items"][0]["attachments"]
    assert [a["text_extraction_status"] for a in attachments] == [
        "not_supported",
        "not_supported",
        "no_extractable_text",
        "failed",
    ]
    assert attachments[3]["text_extraction_error"] == (
        "pdf_text_extraction_failed"
    )
    assert all(a.get("text_path") is None for a in attachments)
    assert all(
        a["content_sha256"]
        == hashlib.sha256(f"downloaded-{a['document_id']}".encode()).hexdigest()
        for a in attachments
    )
    assert result["stats"]["downloaded_attachments"] == 4
    assert result["stats"]["text_extraction_statuses"] == {
        "succeeded": 0,
        "no_extractable_text": 1,
        "not_supported": 2,
        "failed": 1,
    }
    from run_pipeline import convert_escribemeetings_to_scanner_format

    enrichment_input = convert_escribemeetings_to_scanner_format(result)
    assert all(
        attachment["extracted_text"] is None
        for attachment in enrichment_input["action_items"][0]["attachments"]
    )


def test_download_attachment_preserves_image_content_type(tmp_path):
    from escribemeetings_scraper import download_attachment

    response = MagicMock()
    response.headers = {"Content-Type": "image/png; charset=binary"}
    response.content = b"\x89PNG\r\n\x1a\nsource"
    session = MagicMock()
    session.get.return_value = response

    path = download_attachment(session, "70002", tmp_path, "staff image")

    assert path is not None
    assert path.suffix == ".png"
    assert path.read_bytes() == response.content
