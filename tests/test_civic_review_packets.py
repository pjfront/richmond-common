"""Source selection, truthful proposed text, and atomic private packet writes."""
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import civic_review_packets as packets


TODAY = date(2026, 9, 6)


def assertion(**updates):
    row = dict(source="netfile", scope_key="0660620:calendar-2026", record_key="filing1:tx1", content_hash="a" * 64,
               filing_id="filing1", form_type="F460A", transaction_type=0, is_current=True,
               reporting_filer_name="Richmond Committee", reporting_filer_fppc_id="1234567",
               donor_name="Reported Donor, Inc.", donor_fppc_id="7654321", recipient_name="Richmond Committee", recipient_fppc_id="1234567",
               amount=Decimal("5000.00"), amount_kind="monetary", activity_date="2026-09-02", event_kind="receipt",
               source_url="https://netfile.com/Connect2/api/public/image/filing1", source_tier=1,
               reconciliation_status="source_reported", canonical_event_key="event1", review_reason=None,
               raw_payload={"address": "PRIVATE FIXTURE ADDRESS"})
    return {**row, **updates}


def agenda(**updates):
    row = dict(meeting_id="meeting1", source_meeting_guid="guid1", meeting_date="2026-09-15",
               agenda_url="https://richmondca.escribemeetings.com/Meeting.aspx?Id=guid1", body_type="city_council",
               item_number="H-1", title="Flock Safety contract update", source_cancelled_at=None, agenda_source_retired_at=None)
    return {**row, **updates}


def test_date_conflict_packet_preserves_paired_report_values_without_repair():
    periodic = assertion()
    rapid = assertion(record_key="filing2:tx2", filing_id="filing2", transaction_type=20, form_type="F497P1",
                      content_hash="b" * 64, activity_date="2026-09-03", reconciliation_status="pending_review",
                      source_url="https://netfile.com/Connect2/api/public/image/filing2", review_reason="cross_report_date_disagreement")
    result = packets.prepare_finance_packets([rapid, periodic], TODAY)
    engineering = [packet for packet in result if not packet.kind]
    assert len(engineering) == 1
    packet = engineering[0]
    assert [entry["activity_date"] for entry in packet.evidence["reported_entries"]] == ["2026-09-02", "2026-09-03"]
    assert [entry["amount"] for entry in packet.evidence["reported_entries"]] == ["5000.00", "5000.00"]
    assert {entry["source"]["url"] for entry in packet.evidence["reported_entries"]} == {periodic["source_url"], rapid["source_url"]}
    assert "does not merge, delete, or change" in packet.evidence["recommendation"]
    assert "PRIVATE FIXTURE" not in str(packet)


def test_noncash_conflict_packet_packages_both_exact_originals_without_publication():
    from finance_ledger import reconcile
    from test_finance_ledger import noncash_conflict_fixture
    rows = noncash_conflict_fixture()
    reconcile(rows)
    result = packets.prepare_finance_packets(rows, TODAY)
    assert len(result) == 1 and result[0].kind is None
    evidence = result[0].evidence
    assert evidence["reason_codes"] == ["rapid_report_noncash_conflict"]
    assert "does not establish an additional cash receipt" in evidence["reason"][0]
    entries = evidence["reported_entries"]
    assert len(entries) == 2
    assert {entry["source"]["url"] for entry in entries} == {
        "https://netfile.com/Connect2/api/public/image/216815171",
        "https://netfile.com/Connect2/api/public/image/216668328",
    }
    assert {entry["amount_kind"] for entry in entries} == {"monetary", "reported_noncash_value"}
    assert all(entry["activity_date"] == "2026-04-08" and entry["amount"] == "2000.00" for entry in entries)
    assert packets.possible_counterpart(rows[0], rows[1]) and packets.possible_counterpart(rows[1], rows[0])
    assert "does not merge, delete, or change" in evidence["recommendation"]


def test_noncash_comparison_does_not_extend_to_nearby_dates_or_other_forms():
    from test_finance_ledger import noncash_conflict_fixture
    periodic, rapid = noncash_conflict_fixture()
    rapid["activity_date"] = "2026-04-09"
    assert not packets.possible_counterpart(periodic, rapid)
    rapid["activity_date"] = "2026-04-08"
    rapid["transaction_type"] = 21
    assert not packets.possible_counterpart(periodic, rapid)


@pytest.mark.parametrize("updates", [
    {"donor_fppc_id": "1111111"}, {"recipient_fppc_id": None}, {"amount": Decimal("5001")},
    {"activity_date": "2026-07-01"}, {"donor_fppc_id": None, "donor_name": "Reported Donor LLC"},
    {"amount_kind": "negative_adjustment"}, {"transaction_type": 19},
])
def test_comparisons_do_not_use_fuzzy_names_or_date_amount_only(updates):
    assert not packets.possible_counterpart(assertion(), assertion(**updates))


def test_multiplicity_is_one_packet_and_row_order_does_not_change_fingerprint():
    rows = [assertion(record_key=f"filing{i}:tx{i}", content_hash=str(i) * 64, transaction_type=kind,
                      reconciliation_status="pending_review", review_reason="ambiguous_cross_report_multiplicity")
            for i, kind in [(1, 0), (2, 0), (3, 20)]]
    forward = packets.prepare_finance_packets(rows, TODAY)
    reverse = packets.prepare_finance_packets(list(reversed(rows)), TODAY)
    assert len(forward) == 1
    assert len(forward[0].evidence["reported_entries"]) == 3
    assert forward[0].input_fingerprint == reverse[0].input_fingerprint


def test_receipt_brief_uses_each_canonical_event_once_without_election_total_claim():
    row = assertion(reconciliation_status="matched_exact")
    counterpart = assertion(record_key="filing2:tx2", content_hash="b" * 64, filing_id="filing2", form_type="F497P1", transaction_type=20,
                            source_url="https://netfile.com/Connect2/api/public/image/filing2", reconciliation_status="matched_exact")
    result = packets.prepare_finance_packets([row, counterpart], TODAY)
    assert len(result) == 1
    brief = result[0]
    assert brief.kind == "finance_brief"
    assert brief.body.count("$5,000.00") == 1
    assert "not a campaign total" in brief.body
    assert "do not establish" in brief.body
    assert len(brief.sources) == 2
    assert all(source["source_date"] is None for source in brief.sources)
    assert "PRIVATE FIXTURE" not in str(brief)


@pytest.mark.parametrize("updates", [
    {"event_kind": "loan"}, {"amount_kind": "negative_adjustment"}, {"amount": Decimal("-1")},
    {"event_kind": "independent_expenditure"}, {"activity_date": "2026-08-01"}, {"is_current": False},
    {"source_url": "https://unknown.example/filing.pdf"}, {"source_tier": 3}, {"scope_key": "other-city"},
])
def test_unsupported_old_or_untrusted_receipts_do_not_become_public_drafts(updates):
    assert packets.prepare_finance_packets([assertion(**updates)], TODAY) == []


def test_agenda_packet_uses_exact_title_not_generated_summary_and_deduplicates_aliases():
    row = agenda(plain_language_summary="The council approved the contract", topic_label="police")
    alias = agenda(meeting_id="alias1")
    result = packets.prepare_story_packets([row, alias], TODAY)
    assert len(result) == 1
    assert "Flock Safety contract update" in result[0].body
    assert "not recorded decisions" in result[0].body
    assert "approved" not in result[0].body
    assert len(result[0].evidence["agenda_entries"]) == 1
    assert result[0].evidence["agenda_entries"][0]["url"] == "/meetings/meeting1/items/h-1"
    assert result[0].sources[0]["source_date"] == "2026-09-15"


@pytest.mark.parametrize("updates", [
    {"title": "Standard consent calendar"}, {"title": "A flocking pattern"}, {"body_type": "planning_commission"},
    {"source_cancelled_at": "2026-09-01"}, {"agenda_source_retired_at": "2026-09-01"},
    {"meeting_date": "2026-08-01"}, {"title": "Flock <script>source</script>"},
    {"agenda_url": "https://richmondca.gov.evil.example/agenda"}, {"agenda_url": "javascript:alert(1)"},
])
def test_irrelevant_retired_unsafe_or_out_of_window_agendas_are_not_queued(updates):
    assert packets.prepare_story_packets([agenda(**updates)], TODAY) == []


def test_poll_time_is_excluded_but_changed_source_title_changes_fingerprint():
    first = packets.prepare_story_packets([agenda(extracted_at="2026-09-01")], TODAY)[0]
    polled = packets.prepare_story_packets([agenda(extracted_at="2026-09-06")], TODAY)[0]
    changed = packets.prepare_story_packets([agenda(title="Flock Safety contract extension")], TODAY)[0]
    assert first.input_fingerprint == polled.input_fingerprint
    assert first.identity == changed.identity
    assert first.input_fingerprint != changed.input_fingerprint
    moved = packets.prepare_story_packets([agenda(meeting_id="another-database-alias")], TODAY)[0]
    assert moved.input_fingerprint == first.input_fingerprint
    assert replace(first, body="A template copy edit").input_fingerprint == first.input_fingerprint


def connection(*responses, fail_insert=False):
    conn, cur = MagicMock(), MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchone.side_effect = list(responses)
    if fail_insert:
        def execute(sql, params=None):
            if "INSERT INTO pending_decisions" in sql:
                raise RuntimeError("decision insert failed")
        cur.execute.side_effect = execute
    return conn, cur


def test_draft_and_decision_are_created_atomically_with_no_publication_fields():
    packet = packets.prepare_story_packets([agenda()], TODAY)[0]
    conn, cur = connection(None, None, {"id": "draft1", "content_version": 1})
    assert packets.persist_packet(conn, packet) == "created"
    statements = [call.args[0] for call in cur.execute.call_args_list]
    assert "pg_advisory_xact_lock" in statements[0]
    insert = next(sql for sql in statements if "INSERT INTO civic_brief_candidates" in sql)
    assert "status" not in insert and "published" not in insert
    decision = cur.execute.call_args_list[-1].args[1]
    assert decision[4:8] == ("publish_brief", "editorial", "draft1", 1)
    conn.commit.assert_called_once()


def test_failed_decision_write_rolls_back_draft_too():
    packet = packets.prepare_story_packets([agenda()], TODAY)[0]
    conn, _ = connection(None, None, {"id": "draft1", "content_version": 1}, fail_insert=True)
    with pytest.raises(RuntimeError, match="decision insert failed"):
        packets.persist_packet(conn, packet)
    conn.commit.assert_not_called()
    conn.rollback.assert_called_once()


@pytest.mark.parametrize("status", ["pending", "deferred", "approved", "rejected"])
def test_unchanged_input_is_not_regenerated_after_any_judgment(status):
    packet = packets.prepare_story_packets([agenda()], TODAY)[0]
    conn, cur = connection({"id": "old1", "status": status}, None)
    assert packets.persist_packet(conn, packet) == "unchanged"
    assert not any(call.args[0].lstrip().startswith(("INSERT", "UPDATE")) for call in cur.execute.call_args_list)


def test_changed_draft_refreshes_exact_target_version_without_reopening_deferred():
    packet = packets.prepare_story_packets([agenda()], TODAY)[0]
    conn, cur = connection(None, {"id": "decision1", "target_brief_id": "draft1", "action_kind": "publish_brief"},
                          {"status": "draft"}, {"id": "draft1", "content_version": 4})
    assert packets.persist_packet(conn, packet) == "refreshed"
    sql, params = cur.execute.call_args_list[-1].args
    assert "UPDATE pending_decisions" in sql and "status=" not in sql
    assert params[6:9] == ("draft1", 4, "decision1")


def test_reversion_to_rejected_source_revokes_intervening_publish_action():
    packet = packets.prepare_story_packets([agenda()], TODAY)[0]
    conn, cur = connection({"id": "rejected1", "status": "rejected"},
                          {"id": "intervening", "target_brief_id": "draft2", "action_kind": "publish_brief"})
    assert packets.persist_packet(conn, packet) == "refreshed"
    sql = cur.execute.call_args_list[-1].args[0]
    assert "action_kind='resolve_only'" in sql and "target_brief_id=NULL" in sql
    assert "INSERT" not in sql


def test_unchanged_reversion_does_not_advance_a_withdrawn_proposal_again():
    packet = packets.prepare_story_packets([agenda()], TODAY)[0]
    conn, cur = connection({"id": "rejected1", "status": "rejected"},
                          {"id": "intervening", "target_brief_id": None, "action_kind": "resolve_only",
                           "evidence": {"previous_decision_id": "rejected1"}})
    assert packets.persist_packet(conn, packet) == "unchanged"
    assert not any(call.args[0].lstrip().startswith("UPDATE") for call in cur.execute.call_args_list)


def test_subject_allowlist_fails_before_any_database_work():
    packet = replace(packets.prepare_story_packets([agenda()], TODAY)[0], subject="anything-else")
    conn = MagicMock()
    with pytest.raises(ValueError, match="allowlist"):
        packets.persist_packet(conn, packet)
    conn.cursor.assert_not_called()


def test_story_subjects_and_aliases_stay_aligned_with_resident_dossiers():
    source = (Path(__file__).resolve().parents[1] / "web/src/data/civic-stories.ts").read_text(encoding="utf-8")
    for subject, (_, aliases) in packets.SUBJECTS.items():
        assert f"slug: '{subject}'" in source
        for alias in aliases:
            assert f"'{alias}'" in source


def test_large_pending_backlog_fails_explicitly_instead_of_partial_pairing():
    rows = [assertion(record_key=str(i), reconciliation_status="pending_review") for i in range(101)]
    with pytest.raises(ValueError, match="100 pending"):
        packets.prepare_finance_packets(rows, TODAY)


def observed_proposal(**updates):
    packet = packets.prepare_story_packets([agenda()], TODAY)[0]
    return {"id": "decision1", "entity_id": packet.identity, "subject_key": packet.subject,
            "review_version": 2, "target_brief_id": "draft1", "target_content_version": 3, **updates}


@pytest.mark.parametrize("rows", [
    [agenda(source_cancelled_at="2026-09-06", extracted_at="2026-09-01")],
    [agenda(agenda_source_retired_at="2026-09-06", extracted_at="2026-09-01")],
    [], [agenda(title="Routine consent calendar", extracted_at="2026-09-01")],
])
def test_complete_recheck_withdraws_cancelled_retired_removed_or_unrelated_evidence(rows):
    conn, cur = connection()
    observed = observed_proposal()
    cur.fetchall.side_effect = [[observed], rows]
    assert packets.read_story_invalidations(conn, TODAY) == [observed]
    sql = cur.execute.call_args_list[-1].args[0]
    assert "source_cancelled_at IS NULL" not in sql
    assert "agenda_source_retired_at IS NULL" not in sql
    assert "BETWEEN" not in sql
    conn.commit.assert_not_called()
    assert not any(call.args[0].lstrip().startswith(("INSERT", "UPDATE")) for call in cur.execute.call_args_list)


def test_remaining_relevant_evidence_and_aged_out_meetings_keep_existing_proposals():
    conn, cur = connection()
    cur.fetchall.side_effect = [[observed_proposal()], [agenda(meeting_date="2026-05-01")]]
    assert packets.read_story_invalidations(conn, TODAY) == []


def test_source_recheck_failure_is_not_evidence_of_removal():
    conn, cur = connection()
    cur.fetchall.side_effect = [[observed_proposal()], RuntimeError("source read failed")]
    with pytest.raises(RuntimeError, match="source read failed"):
        packets.read_story_invalidations(conn, TODAY)
    assert not any(call.args[0].lstrip().startswith(("INSERT", "UPDATE")) for call in cur.execute.call_args_list)


@pytest.mark.parametrize("opened,rows", [
    ([observed_proposal()] * (packets.MAX_OPEN_STORY_PACKETS + 1), []),
    ([observed_proposal()], [agenda()] * (packets.MAX_AGENDA_ROWS + 1)),
])
def test_incomplete_source_scan_fails_before_any_withdrawal(opened, rows):
    conn, cur = connection()
    cur.fetchall.side_effect = [opened, rows]
    with pytest.raises(ValueError, match="bounded"):
        packets.read_story_invalidations(conn, TODAY)
    assert not any(call.args[0].lstrip().startswith(("INSERT", "UPDATE")) for call in cur.execute.call_args_list)


def test_invalidation_preserves_evidence_and_removes_exact_publish_action_only():
    observed = observed_proposal()
    conn, cur = connection({**observed, "evidence": {"agenda_entries": [{"title": "Flock contract"}]}},
                          {"status": "draft", "content_version": 3})
    assert packets.invalidate_story_packet(conn, observed) == "invalidated"
    sql, params = cur.execute.call_args_list[-1].args
    assert "action_kind='resolve_only'" in sql and "target_brief_id=NULL" in sql
    assert "status=" not in sql
    evidence = params[2].adapted
    assert evidence["agenda_entries"] == [{"title": "Flock contract"}]
    assert evidence["source_invalidation"]["previous_content_version"] == 3
    assert "does not publish" in evidence["recommendation"]
    assert not any("UPDATE civic_brief_candidates" in call.args[0] for call in cur.execute.call_args_list)
    conn.commit.assert_called_once()


@pytest.mark.parametrize("current,candidate", [
    (None, None),
    (observed_proposal(review_version=3), None),
    (observed_proposal(target_brief_id="different-draft"), None),
    (observed_proposal(), {"status": "published", "content_version": 3}),
    (observed_proposal(), {"status": "draft", "content_version": 4}),
])
def test_already_reviewed_or_changed_target_is_not_automatically_withdrawn(current, candidate):
    conn, cur = connection(current, candidate)
    assert packets.invalidate_story_packet(conn, observed_proposal()) == "unchanged"
    assert not any(call.args[0].lstrip().startswith("UPDATE") for call in cur.execute.call_args_list)


def test_returning_eligible_source_refreshes_only_a_still_unjudged_withdrawal():
    packet = packets.prepare_story_packets([agenda()], TODAY)[0]
    conn, cur = connection({"id": "decision1", "status": "deferred"},
                          {"id": "decision1", "target_brief_id": None, "action_kind": "resolve_only", "evidence": {"source_invalidation": {"reason": "withdrawn"}}},
                          {"id": "new-draft", "content_version": 1})
    assert packets.persist_packet(conn, packet) == "refreshed"
    sql, params = cur.execute.call_args_list[-1].args
    assert params[4:8] == ("publish_brief", "editorial", "new-draft", 1)
    assert "status=" not in sql


def test_cli_source_failure_does_not_apply_any_prepared_packets(monkeypatch):
    import db
    import sys
    conn, _ = connection()
    monkeypatch.setattr(db, "get_connection", lambda: conn)
    monkeypatch.setattr(sys, "argv", ["civic_review_packets.py", "--section", "stories", "--apply", "--as-of", str(TODAY)])
    monkeypatch.setattr(packets, "read_inputs", lambda *args: ([], [agenda()]))
    def fail(*args):
        raise RuntimeError("source fetch failed")
    monkeypatch.setattr(packets, "read_story_invalidations", fail)
    writer, invalidator = MagicMock(), MagicMock()
    monkeypatch.setattr(packets, "persist_packet", writer)
    monkeypatch.setattr(packets, "invalidate_story_packet", invalidator)
    with pytest.raises(RuntimeError, match="source fetch failed"):
        packets.main()
    writer.assert_not_called()
    invalidator.assert_not_called()
    conn.close.assert_called_once()
