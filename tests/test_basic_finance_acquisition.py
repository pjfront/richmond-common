"""Bounded official-source transport fixtures; no live calls, writes or models."""
from dataclasses import replace
import json

import pytest

from basic_finance_acquisition import (
    API_BASE, AcquisitionLimits, DEFAULT_LIMITS, FinanceAcquisitionError,
    acquire_bounded_finance_snapshot,
)
from finance_ledger import TYPES
from finance_public_projection import project_public_finance_snapshot


def tx(identity="receipt1", filing="12345", kind=0):
    return dict(id=identity, filingId=filing, transactionType=kind,
                date="2026-05-12", amount="12.34", filerName="Public Committee",
                filerFppcId="1490887", name="Reported Donor", transactionFppcId="951606",
                candidate="Reported Candidate" if kind == 19 else None,
                address="PRIVATE_ADDRESS_NOT_PUBLIC", description="PRIVATE_SOURCE_TEXT")


class Response:
    def __init__(self, body, status=200, *, chunks=None):
        self.body, self.status_code, self.closed, self.chunks = body, status, False, chunks

    def iter_content(self, chunk_size):
        if self.chunks is not None:
            yield from self.chunks
        else:
            for offset in range(0, len(self.body), chunk_size):
                yield self.body[offset:offset + chunk_size]

    def close(self):
        self.closed = True


class Session:
    def __init__(self, transactions=None, *, mutate=None, metadata=None, pdfs=None, status=200):
        self.transactions = transactions or {0: [tx()]}
        self.mutate, self.metadata, self.pdfs, self.status = mutate, metadata or {}, pdfs or {}, status
        self.calls, self.responses, self.closed = [], [], False

    def post(self, url, **options):
        self.calls.append(("post", url, options))
        payload = options["json"]
        rows = self.transactions.get(payload["TransactionType"], [])
        size, page = payload["PageSize"], payload["CurrentPageIndex"]
        value = {"totalMatchingCount": len(rows), "totalMatchingPages": (len(rows) + size - 1) // size,
                 "results": rows[page * size:(page + 1) * size],
                 "searchParameters": {"showSuperceded": False}}
        if self.mutate:
            value = self.mutate(value, payload)
        response = Response(json.dumps(value).encode(), self.status)
        self.responses.append(response)
        return response

    def get(self, url, **options):
        self.calls.append(("get", url, options))
        filing = url.rsplit("/", 1)[-1]
        if "/public/image/" in url:
            body = self.pdfs.get(filing, b"%PDF-invalid-fixture")
        else:
            body = json.dumps(self.metadata.get(filing, {"filingId": filing})).encode()
        response = Response(body, self.status)
        self.responses.append(response)
        return response

    def close(self):
        self.closed = True


def acquire(session, **kwargs):
    return acquire_bounded_finance_snapshot(2026, "2026-10-04", session=session, **kwargs)


def test_real_eight_form_parser_contract_pagination_and_public_projection():
    rows = [tx(f"receipt{index}") for index in range(3)]
    session = Session({0: rows})
    snapshot = acquire(session, limits=replace(DEFAULT_LIMITS, page_size=2))
    assert len(snapshot["assertions"]) == 3 and len(snapshot["coverage"]) == 8
    assert snapshot["acquisition_metrics"]["model_calls"] == 0
    assert snapshot["acquisition_metrics"]["transaction_pages"] == 9
    assert snapshot["acquisition_metrics"]["transaction_records"] == 3
    assert snapshot["acquisition_metrics"]["http_requests"] == 10
    assert snapshot["acquisition_metrics"]["bounded_acquisition"] is True
    assert all(row["snapshot_complete"] and row["status"] == "partial" for row in snapshot["coverage"])
    forms = [options["json"]["TransactionType"] for method, _, options in session.calls if method == "post"]
    assert set(forms) == set(TYPES)
    for method, url, options in session.calls:
        assert url.startswith(API_BASE + "/public/")
        assert options["allow_redirects"] is False and options["stream"] is True
        assert options["timeout"] == (5, 20)
        if method == "post":
            assert options["json"]["Agency"] == 163
            assert options["json"]["ShowSuperceded"] is False
            assert options["json"]["DateStart"] == "2026-01-01"
    assert all(response.closed for response in session.responses)
    assert session.closed is False  # A caller-owned fixture/session is not closed.
    public = project_public_finance_snapshot(snapshot)
    assert len(public["events"]) == 3
    assert "PRIVATE_ADDRESS" not in json.dumps(public, default=str)
    assert "PRIVATE_SOURCE_TEXT" not in json.dumps(public, default=str)


def test_completely_empty_electronic_inventory_remains_explicit_partial_coverage():
    snapshot = acquire(Session({99: []}))
    assert snapshot["assertions"] == [] and snapshot["events"] == []
    assert snapshot["acquisition_metrics"]["http_requests"] == 8
    assert len(project_public_finance_snapshot(snapshot)["coverage"]) == 8


@pytest.mark.parametrize("year,through", [
    (2027, "2027-01-01"), (2026, "2026-11-04"), (2026, "2025-12-31"),
    (True, "2026-10-04"), (2026, "private invalid date"), (2026, None),
])
def test_unreviewed_scope_is_rejected_before_any_source_request(year, through):
    session = Session()
    with pytest.raises(FinanceAcquisitionError):
        acquire_bounded_finance_snapshot(year, through, session=session)
    assert session.calls == []


@pytest.mark.parametrize("limits", [
    replace(DEFAULT_LIMITS, http_requests=513), replace(DEFAULT_LIMITS, pdf_response_bytes=4_000_001),
    replace(DEFAULT_LIMITS, transaction_records=0), replace(DEFAULT_LIMITS, elapsed_seconds=True), {},
])
def test_limits_never_silently_expand_reviewed_maxima(limits):
    session = Session()
    with pytest.raises(FinanceAcquisitionError):
        acquire(session, limits=limits)
    assert session.calls == []


@pytest.mark.parametrize("field,value", [("transaction_records", 1), ("transaction_pages", 1), ("filing_metadata", 1)])
def test_inventory_limits_reject_before_metadata_or_full_pagination(field, value):
    session = Session({0: [tx("one", "filing1"), tx("two", "filing2")]})
    with pytest.raises(FinanceAcquisitionError, match="ceiling"):
        acquire(session, limits=replace(DEFAULT_LIMITS, page_size=1, **{field: value}))
    assert all(method == "post" for method, _, _ in session.calls)
    assert all(response.closed for response in session.responses)


def test_request_limit_stops_instead_of_publishing_incomplete_forms():
    session = Session({99: []})
    with pytest.raises(FinanceAcquisitionError, match="request ceiling"):
        acquire(session, limits=replace(DEFAULT_LIMITS, http_requests=2))
    assert len(session.calls) == 2


@pytest.mark.parametrize("mutate", [
    lambda value, payload: {**value, "totalMatchingCount": True},
    lambda value, payload: {**value, "totalMatchingPages": 1000},
    lambda value, payload: {**value, "results": []},
    lambda value, payload: {**value, "searchParameters": {"showSuperceded": True}},
    lambda value, payload: {**value, "results": [{**value["results"][0], "transactionType": 19}]} if value["results"] else value,
    lambda value, payload: {**value, "results": [{**value["results"][0], "filingId": "../../private"}]} if value["results"] else value,
])
def test_malformed_or_wrong_scope_response_is_not_empty_coverage(mutate):
    session = Session(mutate=mutate)
    with pytest.raises(FinanceAcquisitionError):
        acquire(session)
    assert len(session.calls) == 1


def test_repeated_page_and_changed_total_reject_whole_snapshot():
    repeated = Session({0: [tx("same"), tx("same")]})
    with pytest.raises(FinanceAcquisitionError, match="repeated"):
        acquire(repeated, limits=replace(DEFAULT_LIMITS, page_size=1))
    assert len(repeated.calls) == 2
    def changing(value, payload):
        return {**value, "totalMatchingCount": 3, "totalMatchingPages": 3} if payload["CurrentPageIndex"] else value
    changed = Session({0: [tx("one"), tx("two")]}, mutate=changing)
    with pytest.raises(FinanceAcquisitionError, match="changed"):
        acquire(changed, limits=replace(DEFAULT_LIMITS, page_size=1))


def test_same_opaque_transaction_id_in_distinct_filings_is_not_a_duplicate_page():
    session = Session({0: [tx("same", "filing1"), tx("same", "filing2")]})
    snapshot = acquire(session, limits=replace(DEFAULT_LIMITS, page_size=1))
    assert len(snapshot["assertions"]) == 2
    assert {row["record_key"] for row in snapshot["assertions"]} == {"filing1:same", "filing2:same"}


@pytest.mark.parametrize("field,value", [("agency", 999), ("transactionType", 19),
                                         ("pageSize", 1000), ("currentPageIndex", 1), ("sortOrder", True)])
def test_echoed_wrong_page_or_agency_is_rejected(field, value):
    def mutate(data, payload):
        return {**data, "searchParameters": {"showSuperceded": False, field: value}}
    session = Session(mutate=mutate)
    with pytest.raises(FinanceAcquisitionError, match="page/scope"):
        acquire(session)
    assert len(session.calls) == 1


@pytest.mark.parametrize("status", [301, 302, 401, 404, 429, 500])
def test_http_failure_or_redirect_is_never_retried_or_accepted(status):
    session = Session(status=status)
    with pytest.raises(FinanceAcquisitionError, match="accepted response"):
        acquire(session)
    assert len(session.calls) == 1 and session.responses[0].closed


@pytest.mark.parametrize("field", ["json_response_bytes", "response_total_bytes", "metadata_response_bytes"])
def test_streamed_response_limits_close_before_accepting_oversized_content(field):
    session = Session(metadata={"12345": {"filingId": "12345", "private": "x" * 2_000}})
    with pytest.raises(FinanceAcquisitionError, match="response-byte"):
        acquire(session, limits=replace(DEFAULT_LIMITS, **{field: 32}))
    assert all(response.closed for response in session.responses)


def test_metadata_identity_must_match_requested_filing():
    session = Session(metadata={"12345": {"filingId": "different"}})
    with pytest.raises(FinanceAcquisitionError, match="metadata did not identify"):
        acquire(session)
    assert len(session.calls) == 9


def test_pdf_context_uses_bounded_official_download_once_per_filing(monkeypatch):
    import finance_sync
    contexts = []
    monkeypatch.setattr(finance_sync, "parse_496_context", lambda body, candidate: contexts.append((body, candidate)) or {})
    rows = [tx("ie1", "12345", 19), tx("ie2", "12345", 19)]
    session = Session({19: rows}, pdfs={"12345": b"%PDF-fixture-only"})
    snapshot = acquire(session)
    assert snapshot["acquisition_metrics"]["pdf_downloads"] == 1
    assert snapshot["acquisition_metrics"]["pdf_bytes"] == len(b"%PDF-fixture-only")
    assert len(contexts) == 1
    assert len([url for _, url, _ in session.calls if "/public/image/" in url]) == 1


@pytest.mark.parametrize("field,value", [("pdf_response_bytes", 10), ("pdf_total_bytes", 25), ("pdf_downloads", 1)])
def test_pdf_limits_reject_instead_of_returning_partial_context(monkeypatch, field, value):
    import finance_sync
    monkeypatch.setattr(finance_sync, "parse_496_context", lambda body, candidate: {})
    session = Session({19: [tx("ie1", "filing1", 19), tx("ie2", "filing2", 19)]},
                      pdfs={"filing1": b"%PDF-" + b"x" * 15, "filing2": b"%PDF-" + b"x" * 15})
    with pytest.raises(FinanceAcquisitionError):
        acquire(session, limits=replace(DEFAULT_LIMITS, **{field: value}))
    assert all(response.closed for response in session.responses)


def test_non_pdf_source_body_is_rejected():
    session = Session({19: [tx("ie1", "filing1", 19)]}, pdfs={"filing1": b"<html>error</html>"})
    with pytest.raises(FinanceAcquisitionError, match="accepted PDF"):
        acquire(session)


def test_elapsed_ceiling_is_checked_before_next_request():
    session = Session()
    ticks = iter([0.0, 0.0, 301.0])
    with pytest.raises(FinanceAcquisitionError, match="elapsed-time"):
        acquire(session, clock=lambda: next(ticks))
    assert len(session.calls) == 1 and session.responses[0].closed


def test_unexpected_transport_exception_never_exposes_upstream_or_private_details():
    class Broken(Session):
        def post(self, *args, **kwargs):
            raise ValueError("PRIVATE_DONOR_ADDRESS http://user:password@private")
    with pytest.raises(FinanceAcquisitionError, match="request failed") as error:
        acquire(Broken())
    assert "PRIVATE" not in str(error.value) and "password" not in str(error.value)


def test_default_public_session_disables_netrc_proxy_and_is_closed(monkeypatch):
    import requests
    session = Session({99: []})
    monkeypatch.setattr(requests, "Session", lambda: session)
    acquire_bounded_finance_snapshot(2026, "2026-10-04")
    assert session.trust_env is False and session.closed is True


def test_no_database_or_model_client_is_imported_by_adapter():
    from pathlib import Path
    code = (Path(__file__).resolve().parents[1] / "src/basic_finance_acquisition.py").read_text()
    assert not any(token in code for token in ["import psycopg", "from db", "import openai", "llm_client", "write_bytes(", "write_text("])
