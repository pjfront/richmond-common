import hashlib
import json
from unittest.mock import MagicMock

from finance_ledger import assertion_from_netfile
from test_finance_ledger import transaction


def test_concurrent_document_hash_insert_uses_the_retained_document_id(monkeypatch):
    import db.finance as writer
    tx = transaction()
    assertion = assertion_from_netfile(tx, {"filingId":tx["filingId"]}, "0660620:calendar-2026")
    content_hash = hashlib.sha256(json.dumps(assertion["raw_payload"],sort_keys=True).encode()).hexdigest()
    retained_id = "12345678-1234-1234-1234-123456789012"
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    # Initial lookup sees nothing, but an independent document writer wins the
    # unique hash race. ON CONFLICT returns no newly inserted row.
    cur.fetchall.side_effect = [[], [(content_hash,retained_id)]]
    batch = MagicMock(return_value=[])
    monkeypatch.setattr(writer,"execute_values",batch)
    stats = writer.persist_finance_documents(conn,[assertion],{})
    assert assertion["document_id"] == retained_id
    assert stats == dict(documents_inserted=0,documents_retained=1,document_bytes_inserted=0)
    assert batch.call_count == 1
    assert batch.call_args.kwargs["page_size"] == 250
    assert batch.call_args.kwargs["fetch"] is True


def test_unchanged_document_does_not_attempt_an_insert(monkeypatch):
    import db.finance as writer
    tx = transaction()
    assertion = assertion_from_netfile(tx,{"filingId":tx["filingId"]},"0660620:calendar-2026")
    content_hash = hashlib.sha256(json.dumps(assertion["raw_payload"],sort_keys=True).encode()).hexdigest()
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [(content_hash,"existing-id")]
    batch = MagicMock(side_effect=AssertionError("No insert for unchanged evidence"))
    monkeypatch.setattr(writer,"execute_values",batch)
    stats = writer.persist_finance_documents(conn,[assertion],{})
    assert stats["documents_inserted"] == 0 and assertion["document_id"] == "existing-id"
