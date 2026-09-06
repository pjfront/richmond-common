"""No network/model calls: exercise real image-only PDFs and the real hash writer."""
import hashlib
import json

import fitz
import pytest

from archive_center_discovery import extract_text, save_to_documents


class DocumentConnection:
    """Minimal document store; hashing and insert parameters are production code."""

    def __init__(self):
        self.rows = {}
        self.result = None
        self.commits = 0

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def execute(self, sql, params):
        if sql.startswith("SELECT id FROM documents"):
            row = self.rows.get(params)
            self.result = (row[0],) if row else None
        elif sql.startswith("INSERT INTO documents"):
            self.rows[(params[1], params[7])] = params
        else:
            raise AssertionError(f"Unexpected statement: {sql}")

    def fetchone(self):
        return self.result

    def commit(self):
        self.commits += 1


def scanned_pdf(path, shade=100):
    document = fitz.open()
    page = document.new_page(width=100, height=100)
    pixels = fitz.Pixmap(fitz.csRGB, (0, 0, 10, 10))
    pixels.clear_with(shade)
    page.insert_image(page.rect, pixmap=pixels)
    content = document.tobytes()
    document.close()
    path.write_bytes(content)
    assert extract_text(path) is None
    return content


def test_scanned_pdf_preserves_bytes_and_identity_on_replay(tmp_path):
    path = tmp_path / "scanned.pdf"
    original = scanned_pdf(path)
    doc = {"adid": "17838", "amid": 67, "title": "143-26", "text": None, "pdf_path": path}
    conn = DocumentConnection()

    first = save_to_documents(conn, [doc], "0660620")
    assert first["inserted"] == 1
    assert first["errors"] == 0
    key = ("0660620", hashlib.sha256(original).hexdigest())
    row = conn.rows[key]
    original_id = row[0]
    assert row[5].adapted == original
    assert row[6] is None
    assert row[3] == "https://www.ci.richmond.ca.us/Archive.aspx?ADID=17838"
    assert json.loads(row[10])["text_extraction_status"] == "unavailable"
    assert json.loads(row[10])["raw_content_format"] == "pdf_bytes"

    second = save_to_documents(conn, [doc], "0660620")
    assert second["inserted"] == 0
    assert second["deduplicated"] == 1
    assert conn.rows[key][0] == original_id
    assert len(conn.rows) == 1

    # Different scans must never collapse to the same empty-text hash.
    another = tmp_path / "another.pdf"
    scanned_pdf(another, shade=200)
    third = save_to_documents(conn, [{**doc, "adid": "17810", "pdf_path": another}], "0660620")
    assert third["inserted"] == 1
    assert len(conn.rows) == 2


def test_text_records_retain_existing_hash_and_uuid_even_with_pdf(tmp_path):
    conn = DocumentConnection()
    text = "  Adopted resolution.\n"
    doc = {"adid": "17785", "amid": 67, "text": text}
    save_to_documents(conn, [doc], "0660620")
    key = ("0660620", hashlib.sha256(text.encode()).hexdigest())
    identity = conn.rows[key][0]
    path = tmp_path / "source.pdf"
    scanned_pdf(path)
    result = save_to_documents(conn, [{**doc, "pdf_path": path}], "0660620")
    assert result["deduplicated"] == 1
    assert len(conn.rows) == 1
    assert conn.rows[key][0] == identity


@pytest.mark.parametrize("content", [b"", b"<html>City error page</html>"])
def test_missing_or_non_pdf_evidence_never_creates_a_document(tmp_path, content):
    path = tmp_path / "not-a-pdf.pdf"
    path.write_bytes(content)
    conn = DocumentConnection()
    result = save_to_documents(conn, [{"adid": "1", "text": " \n", "pdf_path": path}], "0660620")
    assert result["errors"] == 1
    assert conn.rows == {}


def test_sync_carries_the_downloaded_scan_to_persistence(tmp_path, monkeypatch):
    from unittest.mock import MagicMock
    import archive_center_discovery as discovery
    from pipelines.archive_center import sync_archive_center

    path = tmp_path / "scan.pdf"
    original = scanned_pdf(path)
    session = MagicMock()
    monkeypatch.setattr(discovery, "create_session", lambda: session)
    monkeypatch.setattr(discovery, "enumerate_amids", lambda _: {67: {"name": "Council Resolutions"}})
    monkeypatch.setattr(discovery, "_parse_document_list", lambda _: [{"adid": "17838", "title": "143-26"}])
    monkeypatch.setattr(discovery, "download_document", lambda *args: path)
    conn = DocumentConnection()
    result = sync_archive_center(conn, "0660620")
    assert result["records_new"] == 1
    assert result["records_errors"] == 0
    assert conn.rows[("0660620", hashlib.sha256(original).hexdigest())][5].adapted == original


def test_new_scan_budget_is_bounded_and_replay_makes_progress(tmp_path):
    paths = [tmp_path / f"scan-{n}.pdf" for n in range(3)]
    for index, path in enumerate(paths):
        scanned_pdf(path, shade=80 + index)
    docs = [{"adid": str(100 + i), "text": None, "pdf_path": path} for i, path in enumerate(paths)]
    docs.append({"adid": "50", "text": "Existing text import still works."})
    conn = DocumentConnection()
    first = save_to_documents(conn, docs, "0660620", max_new_scan_documents=1)
    assert first["scans_inserted"] == 1
    assert first["scans_deferred"] == 2
    assert first["inserted"] == 2  # Independent text work continues.
    assert first["total"] == 4
    assert {row[4] for row in conn.rows.values()} == {"archive_center_ADID_102", "archive_center_ADID_50"}

    second = save_to_documents(conn, docs, "0660620", max_new_scan_documents=1)
    assert second["scans_inserted"] == 1
    assert second["scans_deferred"] == 1
    assert second["scans_retained"] == 2
    assert second["deduplicated"] == 2
    assert second["total"] == 4


def test_new_scan_byte_budget_never_counts_existing_hashes(tmp_path):
    path = tmp_path / "scan.pdf"
    content = scanned_pdf(path)
    docs = [{"adid": "1", "text": None, "pdf_path": path}]
    conn = DocumentConnection()
    blocked = save_to_documents(conn, docs, "0660620", max_new_scan_bytes=len(content) - 1)
    assert blocked["scans_deferred"] == 1
    assert conn.rows == {}
    first = save_to_documents(conn, docs, "0660620", max_new_scan_bytes=len(content))
    assert first["scan_bytes_inserted"] == len(content)
    replay = save_to_documents(conn, docs, "0660620", max_new_scan_bytes=0, max_new_scan_documents=0)
    assert replay["deduplicated"] == 1
    assert replay["scans_deferred"] == 0
    assert replay["scan_bytes_inserted"] == 0


def test_failed_evidence_is_not_reported_as_complete(tmp_path, monkeypatch):
    from unittest.mock import MagicMock
    import archive_center_discovery as discovery
    from pipelines.archive_center import sync_archive_center

    monkeypatch.setattr(discovery, "create_session", MagicMock)
    monkeypatch.setattr(discovery, "enumerate_amids", lambda _: {67: {"name": "Council Resolutions"}})
    monkeypatch.setattr(discovery, "_parse_document_list", lambda _: [{"adid": "17838", "title": "143-26"}])
    monkeypatch.setattr(discovery, "download_document", lambda *args: None)
    conn = DocumentConnection()
    result = sync_archive_center(conn, "0660620")
    assert result["records_errors"] == 1
    assert result["required_source_incomplete"] is True
    assert result["records_deferred"] == 0
    assert conn.rows == {}
