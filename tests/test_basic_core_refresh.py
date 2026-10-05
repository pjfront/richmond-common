from datetime import date
import json

import pytest

from basic_core_refresh import (CompactRefreshError, acquire_agendas, check_storage,
                                normalize_observation, refresh_compact, write_agendas)
from basic_refresh import RefreshGuardError, apply_refresh, validate_public_target

GUID = "ba1cfe4c-0d53-454a-985a-810b28a8c12e"
HTML = """<h1>City Council</h1><div class='AgendaItemContainer'>
<div class='AgendaItemCounter'>I.1.</div><div class='AgendaItemTitle'>Chevron air quality permit</div>
<div class='AgendaItemDescription'>Official agenda text.</div>
<a href='filestream.ashx?DocumentId=9876'>Staff report PDF</a></div>"""
RAW = {"ID": GUID, "MeetingName": "City Council", "StartDate": "2026/10/06 18:00:00", "HasAgenda": True}


class Response:
    def __init__(self, body, status=200):
        self.body, self.status_code, self.closed = body, status, False
    def raise_for_status(self):
        pass
    def iter_content(self, chunk_size):
        yield self.body
    def close(self):
        self.closed = True


class Session:
    def __init__(self, rows=None, html=HTML):
        self.rows, self.html, self.calls = rows or [RAW], html, []
    def post(self, url, **options):
        self.calls.append(("post", url, options))
        return Response(json.dumps({"d": self.rows}).encode())
    def get(self, url, **options):
        self.calls.append(("get", url, options))
        return Response(self.html.encode())


def test_fixture_source_adapter_fetches_only_calendar_and_html_never_pdf():
    session = Session()
    observations = acquire_agendas(today=date(2026, 10, 4), session=session)
    assert observations[0]["state"] == "complete_agenda"
    assert observations[0]["items"][0]["item_number"] == "I.1"
    assert len(observations[0]["revision"]) == 64
    assert len(session.calls) == 2
    assert all("filestream" not in url for _, url, _ in session.calls)
    assert all(options["allow_redirects"] is False and options["stream"] is True for _, _, options in session.calls)
    assert "attachments" not in observations[0]["items"][0]


def test_stub_and_unpublished_agendas_do_not_prove_withdrawal():
    assert normalize_observation(RAW, "<h1>City Council</h1>")["state"] == "legacy_portal_stub"
    assert normalize_observation({**RAW, "HasAgenda": None}, None)["state"] == "awaiting_agenda"
    assert normalize_observation({**RAW, "HasAgenda": False}, None)["state"] == "withdrawn"


def test_duplicate_source_identity_or_truncated_window_is_rejected():
    with pytest.raises(CompactRefreshError, match="duplicate"):
        acquire_agendas(today=date(2026, 10, 4), session=Session([RAW, RAW]))
    another = {**RAW, "ID": "aa1cfe4c-0d53-454a-985a-810b28a8c12e"}
    with pytest.raises(CompactRefreshError, match="cohort"):
        acquire_agendas(today=date(2026, 10, 4), session=Session([RAW, another]), limit=1)


def test_ambiguous_items_reject_whole_observation():
    with pytest.raises(CompactRefreshError, match="ambiguous"):
        normalize_observation(RAW, HTML + HTML)


def test_partial_layout_with_unnumbered_actionable_item_cannot_retire_retained_rows():
    unnumbered="<div class='AgendaItemContainer'><div class='AgendaItemTitle'>A new unnumbered contract</div></div>"
    with pytest.raises(CompactRefreshError,match="Unnumbered"):
        normalize_observation(RAW,HTML+unnumbered)


def test_parser_skipped_actionable_container_cannot_authorize_retirement():
    omitted="<div class='AgendaItemContainer'><div class='RichText'>Unsupported revised actionable record</div></div>"
    with pytest.raises(CompactRefreshError,match="Unsupported"):
        normalize_observation(RAW,HTML+omitted)
    assert normalize_observation(RAW,HTML+"<div class='AgendaItemContainer'></div>")["state"] == "complete_agenda"


class Cursor:
    def __init__(self, *, authority="agenda", size=48_000_000):
        self.authority, self.size = authority, size
        self.queries, self.answer, self.rowcount = [], [], 1
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def execute(self, query, params=None):
        self.queries.append((query, params))
        if "pg_database_size" in query:
            self.answer = [(self.size,)]
        elif "FROM bodies" in query:
            self.answer = [("City Council", "c1b82dc9-23d0-446e-8f5f-224a6bd4269d")]
        elif "FROM topics" in query:
            self.answer = [("chevron", "b054d91a-69da-47cd-b53a-af81a146e0b8", "Chevron & the Refinery")]
        elif "SELECT id, source_meeting_guid" in query:
            self.answer = [("5f560013-daea-499a-8ecd-ca1a089c8a0c", GUID, None,"2026-10-06","c1b82dc9-23d0-446e-8f5f-224a6bd4269d","regular")]
        elif "SELECT id, item_number" in query:
            self.answer = [("9cf375c8-edc1-413c-8ee0-6485348fbc6f", "I.1", self.authority)]
        else:
            self.answer = []
    def fetchone(self):
        return self.answer[0] if self.answer else None
    def fetchall(self):
        return self.answer


def test_writer_preserves_retained_item_and_meeting_uuids_and_never_rewrites_votes():
    cur = Cursor()
    result = write_agendas(cur, [normalize_observation(RAW, HTML)])
    insert = [(q, p) for q, p in cur.queries if "INSERT INTO agenda_items" in q]
    assert insert[0][1][0] == "9cf375c8-edc1-413c-8ee0-6485348fbc6f"
    assert insert[0][1][1] == "5f560013-daea-499a-8ecd-ca1a089c8a0c"
    assert result["tags_written"] == 1
    assert not any(re.search(r"(DELETE|UPDATE|INSERT INTO) (votes|motions)", q) for q, _ in cur.queries)
    assert not any("documents" in q for q, _ in cur.queries)
    retired = [q for q, _ in cur.queries if "UPDATE agenda_items SET agenda_source_retired_at" in q]
    assert "agenda_source_authority='agenda'" in retired[0]


def test_minutes_owned_item_is_not_overwritten_and_stub_never_retires():
    cur = Cursor(authority="minutes")
    result = write_agendas(cur, [normalize_observation(RAW, HTML)])
    assert result["minutes_preserved"] == 1
    assert not any("INSERT INTO agenda_items" in q for q, _ in cur.queries)
    cur = Cursor()
    write_agendas(cur, [normalize_observation(RAW, "<h1>Empty stub</h1>")])
    assert not any("agenda_source_retired_at=now()" in q for q, _ in cur.queries)


def test_same_guid_reschedule_is_held_before_any_write():
    cur=Cursor()
    observation=normalize_observation({**RAW,"StartDate":"2026/10/13 18:00:00"},HTML)
    with pytest.raises(CompactRefreshError,match="reschedule"):
        write_agendas(cur,[observation])
    assert all(q.lstrip().startswith("SELECT") for q,_ in cur.queries)


def test_keyword_projection_reconciliation_does_not_remove_manual_tags():
    cur=Cursor()
    write_agendas(cur,[normalize_observation(RAW,HTML)])
    deletions=[(q,p) for q,p in cur.queries if "DELETE FROM item_topics" in q]
    assert "source='keyword'" in deletions[0][0]
    assert deletions[0][1][1] == ["b054d91a-69da-47cd-b53a-af81a146e0b8"]


def test_storage_headroom_fails_before_mutation():
    cur = Cursor(size=451_000_000)
    with pytest.raises(CompactRefreshError, match="headroom"):
        check_storage(cur)
    assert len(cur.queries) == 1 and cur.queries[0][0].startswith("SELECT")
    with pytest.raises(CompactRefreshError, match="500 MB"):
        check_storage(Cursor(), ceiling=1_000_000_000)


@pytest.mark.parametrize("ref,url", [
    ("ahrwvmizzykyyfavdvfv", "postgresql://user:private@db.ahrwvmizzykyyfavdvfv.supabase.co/postgres?sslmode=require"),
    ("abcdefghijklmnopqrst", "postgresql://user:private@db.other.supabase.co/postgres?sslmode=require"),
    ("abcdefghijklmnopqrst", "postgresql://user:private@db.abcdefghijklmnopqrst.supabase.co/postgres?sslmode=require&host=paid.invalid"),
    ("abcdefghijklmnopqrst", "postgresql://user:private@db.abcdefghijklmnopqrst.supabase.co/postgres"),
])
def test_public_target_exact_identity_tls_and_paid_project_exclusion(ref, url):
    with pytest.raises(RefreshGuardError) as error:
        validate_public_target(url, ref)
    assert "private" not in str(error.value)


def test_public_target_requires_readiness_before_connection(monkeypatch):
    monkeypatch.setenv("RICHMOND_BASIC_DATABASE_URL", "postgresql://user:private@db.abcdefghijklmnopqrst.supabase.co/postgres?sslmode=require")
    monkeypatch.delenv("RICHMOND_BASIC_READY", raising=False)
    # Target readiness remains required even with a verified writer policy.
    from feature_policy import load_policy
    policy = load_policy()
    policy["storage"]["basic_public"]["writerReady"] = True
    with pytest.raises(RefreshGuardError, match="readiness"):
        apply_refresh("basic_public", target="public", policy=policy)


def test_exact_declared_session_pooler_supports_ipv4_without_paid_addon():
    host="aws-0-us-west-1.pooler.supabase.com"
    ref="abcdefghijklmnopqrst"
    url=f"postgresql://postgres.{ref}:private@{host}:5432/postgres?sslmode=require"
    validate_public_target(url,ref,host)
    for untrusted in (None,"aws-0-us-east-1.pooler.supabase.com","proxy.example.invalid"):
        with pytest.raises(RefreshGuardError):
            validate_public_target(url,ref,untrusted)
    for bad in (url.replace(":5432",":6543"),url.replace(ref+":private","otherproject:private"),url+"&host=paid.invalid"):
        with pytest.raises(RefreshGuardError):
            validate_public_target(bad,ref,host)


def test_finance_window_stops_before_acquisition_and_no_implicit_year_rollover():
    with pytest.raises(CompactRefreshError, match="2026 publication"):
        refresh_compact(None, ["finance"], year=2027, through="2027-01-01", ceiling=500_000_000)


import re
